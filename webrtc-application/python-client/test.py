from aiortc import VideoStreamTrack
from av import VideoFrame

a = VideoStreamTrack()
print(a._id)

b = VideoFrame()
print(b._id)