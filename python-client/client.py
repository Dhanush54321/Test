# robot.py
import asyncio
import uuid
import cv2
import numpy as np
import socketio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, VideoStreamTrack
from av import VideoFrame
from config import SIGNALING_SERVER_URL, CAMERA_INDEX, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS

sio = socketio.AsyncClient()
pc = None
dc = None
video_track = None
current_viewer_id = None

class WebcamVideoTrack(VideoStreamTrack):
    def __init__(self, camera_index):
        super().__init__()  # don't forget base init
        self.camera_index = camera_index
        self.cap = cv2.VideoCapture(self.camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
        if not self.cap.isOpened():
            raise RuntimeError("Could not open webcam")
        self._enabled = True
        print("[Robot] Webcam initialized")

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        if not self._enabled:
            black = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(black, format="rgb24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

        ret, frame = self.cap.read()
        if not ret:
            black = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(black, format="rgb24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        avf = VideoFrame.from_ndarray(frame, format="rgb24")
        avf.pts = pts
        avf.time_base = time_base
        return avf

    def enable(self):
        self._enabled = True
        print("[Robot] Video enabled")

    def disable(self):
        self._enabled = False
        print("[Robot] Video disabled")

    def stop(self):
        if self.cap:
            self.cap.release()
            print("[Robot] Webcam released")


@sio.event
async def connect():
    print("[Robot] connected to signaling server")
    await sio.emit("register-robot")


@sio.event
async def registered_as_robot():
    print("[Robot] Registered as robot on server")


@sio.event
async def viewer_waiting():
    print("[Robot] A viewer is waiting (server notified)")


@sio.event
async def offer(data):
    """
    data: { sdp, type, from }
    'from' is viewer socket id so we can send answer back
    """
    global pc, dc, video_track, current_viewer_id

    print("[Robot] Offer received from viewer")
    current_viewer_id = data.get("from")

    # if existing pc, clean it up (full close) then recreate
    if pc:
        await cleanup(full=True)

    ice_servers = [
        RTCIceServer(urls=["stun:stun.l.google.com:19302"])
    ]
    configuration = RTCConfiguration(iceServers=ice_servers)
    pc = RTCPeerConnection(configuration)

    # Create video sender by adding a track (attempt to create webcam initially)
    try:
        video_track = WebcamVideoTrack(CAMERA_INDEX)
        video_sender = pc.addTrack(video_track)
        print("[Robot] Added initial video track to peer")
    except Exception as e:
        print("[Robot] Could not open webcam initially:", e)
        video_track = None

    @pc.on("datachannel")
    def on_datachannel(channel):
        global dc
        dc = channel
        print("[Robot] DataChannel opened:", channel.label)

        @channel.on("message")
        def on_message(msg):
            print("[Robot] Received datachannel message:", msg)
            # viewer commands
            if msg == "start-camera":
                asyncio.create_task(handle_start_camera())
                channel.send("camera-started-ack")
            elif msg == "stop-camera":
                asyncio.create_task(handle_stop_camera())
                channel.send("camera-stopped-ack")
            else:
                channel.send(f"echo:{msg}")

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            # send candidate to viewer
            await sio.emit("candidate", {"to": current_viewer_id, "candidate": {
                "candidate": candidate.candidate,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex
            }})

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("[Robot] PC connectionState:", pc.connectionState)
        if pc.connectionState in ("failed", "closed"):
            print("[Robot] PC closed/fail - cleaning up")
            await cleanup(full=True)

    # set remote, create answer, send back
    await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type=data["type"]))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    await sio.emit("answer", {"to": current_viewer_id, "sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    print("[Robot] Sent answer to viewer")

    # inform server & viewers robot is ready
    await sio.emit("robot-ready-for-offers")

async def handle_start_camera():
    global pc, video_track
    if not pc:
        print("[Robot] No active pc to start camera")
        return

    # If a track already exists we may only need to enable it
    if video_track:

        try:
            video_track.enable()
            print("[Robot] Re-enabled existing video track")
            return
        except Exception as e:
            print("[Robot] Failed to re-enable existing track:", e)

    # create a new track and replace any sender's track
    try:
        new_track = WebcamVideoTrack(CAMERA_INDEX)
        for sender in pc.getSenders():
            if sender.kind == "video":
                await sender.replace_track(new_track)
                video_track = new_track
                print("[Robot] Replaced sender track with new webcam track")
                return

        # if no video sender found, add a new sender
        pc.addTrack(new_track)
        video_track = new_track
        print("[Robot] Added webcam track as new sender")
    except Exception as e:
        print("[Robot] Failed to start camera:", e)

async def handle_stop_camera():
    global pc, video_track
    if not pc:
        print("[Robot] No active pc to stop camera")
        return

    if not video_track:
        print("[Robot] No video track to stop")
        return

    try:
        # find the sender that has this track and replace with None
        for sender in pc.getSenders():
            if sender.track == video_track:
                await sender.replace_track(None)
                break
        # release camera resources locally
        video_track.stop()
        video_track = None
        print("[Robot] Camera stopped and track removed (PC still alive)")
    except Exception as e:
        print("[Robot] Failed to stop camera:", e)


@sio.event
async def candidate(data):
    # incoming candidate from viewer
    global pc
    try:
        # aiortc wants dict form passed to addIceCandidate, but python-socketio sends separately;
        # we just create candidate object by using addIceCandidate with dict.
        candidate = data
        if pc:
            await pc.addIceCandidate(candidate)
            print("[Robot] Added ICE candidate from viewer")
    except Exception as e:
        print(" ")

        


@sio.event
async def disconnect():
    print("[Robot] disconnected from server")
    await cleanup(full=True)


async def cleanup(full=True):
    global pc, video_track, dc, current_viewer_id
    if video_track:
        try:
            video_track.stop()
        except Exception:
            pass
        video_track = None
    if full and pc:
        try:
            await pc.close()
        except Exception:
            pass
        pc = None
    dc = None
    current_viewer_id = None
    print("[Robot] cleanup done (full={})".format(full))


async def main():
    await sio.connect(SIGNALING_SERVER_URL)
    print("[Robot] connected to", SIGNALING_SERVER_URL)
    await sio.wait()

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        print("exiting")
