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
from config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, CAMERA_INDEX
sio = socketio.AsyncClient()
pc = None
dc = None
video_track = None

class WebcamVideoTrack(VideoStreamTrack):
    def __init__(self,camera_index):

        self.camera_index = camera_index
        # self.cap = cv2.VideoCapture("/home/dhanush/Downloads/Testing/webrtc-application/web-client/videoplayback.mp4")  
        self.cap = cv2.VideoCapture(self.camera_index)
        print(self.cap.isOpened())
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
        
        
        if not self.cap.isOpened():
            raise RuntimeError("Could not open webcam")
        
        self._id = str(uuid.uuid4())  # Unique ID for track
        self.kind = "video" 
        self._readyState = "live"                  # aiortc expects this
        self._MediaStreamTrack__ended = False 
        
        print(f"[Backend] Webcam initialized: {VIDEO_WIDTH}x{VIDEO_HEIGHT} @ {VIDEO_FPS}fps")

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        
        ret, frame = self.cap.read()
        if not ret:
            print("[Backend] Failed to capture frame")
            return None
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        print(frame)
        
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        print("frame captured")
        
        return av_frame
    
    def stop(self):
        if self.cap:
            self.cap.release()
            print("[Backend] Webcam released")

@sio.event
async def connect():
    print("[Backend] Connected to signaling server")
    await sio.emit("register-robot")
    await sio.emit("robot-registered")

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

    # Create RTCConfiguration with proper ice servers
    configuration = RTCConfiguration(iceServers=ice_servers)
    pc = RTCPeerConnection(configuration)

    # Initialize webcam video track
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
                response = "Video streaming started"
            elif message == "stop-video":
                print("[Backend] Video streaming stop requested")
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

    await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type=data["type"]))

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    await sio.emit("answer", {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })
    print("[Backend] Sent answer")

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

async def cleanup():
    global pc, video_track
    if video_track:
        video_track.stop()
        video_track = None
    if pc:
        await pc.close()
        pc = None
    print("[Backend] Cleanup completed")


async def main():
    try:
        print("[Backend] Starting robot application...")
        await sio.connect("https://test-e0et.onrender.com")
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