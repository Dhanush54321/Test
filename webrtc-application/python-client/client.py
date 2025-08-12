import socketio
import asyncio
import cv2
import numpy as np
import uuid
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, VideoStreamTrack, RTCConfiguration, RTCIceServer
from aiortc.contrib.signaling import BYE
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame
import threading
import time
from config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, CAMERA_INDEX, SIGNALING_SERVER_URL
sio = socketio.AsyncClient()
pc = None
dc = None
video_track = None

class WebcamVideoTrack(VideoStreamTrack):
    def __init__(self, camera_index):
        self.camera_index = camera_index
        self.cap = cv2.VideoCapture(self.camera_index)
        print(self.cap.isOpened())
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
        
        if not self.cap.isOpened():
            raise RuntimeError("Could not open webcam")
        
        self._id = str(uuid.uuid4())  
        self.kind = "video" 
        self._readyState = "live"                 
        self._MediaStreamTrack__ended = False 
        self._enabled = True  
        
        print(f"[Backend] Webcam initialized: {VIDEO_WIDTH}x{VIDEO_HEIGHT} @ {VIDEO_FPS}fps")

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        
        if not self._enabled:
            
            black_frame = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
            av_frame = VideoFrame.from_ndarray(black_frame, format="rgb24")
            av_frame.pts = pts
            av_frame.time_base = time_base
            return av_frame
        
        ret, frame = self.cap.read()
        if not ret:
            print("[Backend] Failed to capture frame")
            black_frame = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
            av_frame = VideoFrame.from_ndarray(black_frame, format="rgb24")
            av_frame.pts = pts
            av_frame.time_base = time_base
            return av_frame
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        print(frame)
        
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        print("frame captured")
        
        return av_frame
    
    def enable_video(self):
        """Enable video streaming"""
        self._enabled = True
        print("[Backend] Video streaming enabled")
    
    def disable_video(self):
        """Disable video streaming (sends black frames)"""
        self._enabled = False
        print("[Backend] Video streaming disabled")
    
    def stop(self):
        if self.cap:
            self.cap.release()
            print("[Backend] Webcam released")


async def start_video_track():
    global video_track,pc
    
    if not pc:
        print("[Backend] No active peer connection to start available")
        return
    
    if video_track:
        print("[Backend] Video track already started")
        return  
    try:
        video_track = WebcamVideoTrack(CAMERA_INDEX)
        for sender in pc.getSenders():
            if sender.track is None and sender.kind == "video":
                await sender.replace_track(video_track)
                break
        print("[Backend] Video streaming enabled")
    
    except Exception as e:
        print(f"[Backend] Failed to enable video: {e}")

async def stop_video_track():
    global video_track,pc

    if not pc:
        print("[Backend] No active peer connection to stop video")
        return
    
    if not video_track:
        print("[Backend] No video track available")
        return
        
    try:
        for sender in pc.getSenders():
            if sender.track == video_track:
                await sender.replace_track(None)
                break
        video_track.stop()
        video_track = None
        print("[Backend] Video streaming disabled (track removed, connection alive)")
    except Exception as e:
        print(f"[Backend]  Failed to disable video: {e}")

@sio.event
async def connect():
    print("[Backend] Connected to signaling server")
    await sio.emit("register-robot")
    print("[Backend] Robot registered - waiting for frontend pairing...")

@sio.event
async def robot_accepted():
    print("[Backend] Robot registration accepted")

@sio.event 
async def frontend_ready():
    print("[Backend] Frontend paired - initializing WebRTC...")


@sio.event
async def offer(data):
    global pc, dc, video_track
    print("[Backend] Offer received:", data)

    if pc:
        print("[Backend] Existing peer connection found, closing it")
        await cleanup()

    ice_servers = [
        RTCIceServer(urls=["stun:139.59.66.172:3478"]),
        # RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
        # RTCIceServer(urls=["stun:stun2.l.google.com:19302"]),
        
        # RTCIceServer(urls=["stun:bn-turn1.xirsys.com"]),
        
      
        # RTCIceServer(
        #     urls=[
        #         "turn:bn-turn1.xirsys.com:80?transport=udp",
        #         "turn:bn-turn1.xirsys.com:80?transport=tcp",
        #         "turns:bn-turn1.xirsys.com:443?transport=tcp"
        #     ],
        #     username="Jc0EzhdGBYiCzaKjrC1P7o2mcXTo6TlM_E9wjvXn16Eqs7ntsZaGMeRVAxM4m31rAAAAAGhTqu5CYXJhdGg=",
        #     credential="c0f43e62-4cd4-11f0-aba7-0242ac140004"
        # ),
        
        
        RTCIceServer(
            urls=["turn:139.59.66.172:3478"],
            username="robotcoturn",
            credential="robot@123"
        )
    ]

    configuration = RTCConfiguration(iceServers=ice_servers)
    pc = RTCPeerConnection(configuration)

    try:
        video_track = WebcamVideoTrack(CAMERA_INDEX)
        pc.addTrack(video_track)
        print("[Backend] Video track added to peer connection")
    except Exception as e:
        print(f"[Backend] Failed to initialize webcam: {e}")
        video_track = None

    @pc.on("datachannel")
    def on_datachannel(channel):
        global dc
        dc = channel
        print("[Backend] Data channel opened:", channel.label)

        @channel.on("message")
        def on_message(message):
            print(f"[Backend] Received message from frontend: {message}")
            
            if message == "start-video":
                print("[Backend] Video streaming requested")
                asyncio.create_task(start_video_track())
                response = "Video streaming started"
            elif message == "stop-video":
                print("[Backend] Video streaming stop requested")
                asyncio.create_task(stop_video_track())
                response = "Video streaming stopped"
            else:
                response = f"Ack: {message}"
            
            print(f"[Backend] Sending response: {response}")
            channel.send(response)

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            print(f"[Backend] Sending ICE candidate: {candidate.candidate[:50]}...")
            await sio.emit("candidate", {
                "candidate": candidate.candidate,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex
            })
        else:
            print("[Backend] ICE gathering completed")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"[Backend] Connection state changed: {pc.connectionState}")
        # if pc.connectionState == "failed":
        #     print("[Backend] Connection failed, cleaning up...")
        #     await cleanup()

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        print(f"[Backend] ICE connection state changed: {pc.iceConnectionState}")
        
    @pc.on("icegatheringstatechange")
    async def on_icegatheringstatechange():
        print(f"[Backend] ICE gathering state changed: {pc.iceGatheringState}")

    await sio.emit("robot-ready-for-offers")
    print("[Backend] Peer connection ready, signaled server")

    await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type=data["type"]))

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    await sio.emit("answer", {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })
    print("[Backend] Sent answer")
    
    await sio.emit("robot-ready-for-offers")
    print("[Backend]  Robot ready for additional offers")

@sio.event
async def candidate(data):
    global pc
    print("[Backend] ICE candidate received:", data)
    if pc:
        try:
            parsed = candidate_from_sdp(data["candidate"])
            parsed.sdpMid = data["sdpMid"]
            parsed.sdpMLineIndex = data["sdpMLineIndex"]

            await pc.addIceCandidate(parsed)
            print("[Backend] ICE candidate added successfully")

        except Exception as e:
            print(f"[Backend] Failed to add ICE candidate: {e}")

@sio.event
async def disconnect():
    print("[Backend] Disconnected from signaling server")
    await cleanup()

@sio.event
async def robot_disconnect():
    print("[Backend] Robot disconnected from signaling server")
    await cleanup()

async def cleanup(full = True):
    global pc, video_track
    if video_track:
        video_track.stop()
        video_track = None
    if pc and full:
        await pc.close()
        pc = None
    print("[Backend] Cleanup completed")


async def main():
    try:
        print("[Backend] Starting robot application...")
        print(f"[Backend] Connecting to: {SIGNALING_SERVER_URL}")
        await sio.connect(SIGNALING_SERVER_URL)
        print("[Backend] Connected to signaling server, waiting for connections...")
        await sio.wait()
    except KeyboardInterrupt:
        print("[Backend] Shutting down...")
        await cleanup()
    except Exception as e:
        print(f"[Backend] Error: {e}")
        await cleanup()


if __name__ == "__main__":
    asyncio.run(main())