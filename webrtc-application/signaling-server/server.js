const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const cors = require("cors");

const app = express();
const server = http.createServer(app); 

const PORT = process.env.PORT || 9010;


const allowedOrigins = [
  "http://localhost:5500",
  "http://127.0.0.1:5500",
  "http://localhost:3000",
  "https://application-8mai.onrender.com",
  "https://incredible-rugelach-0de508.netlify.app"
];

app.use(cors({
  origin: allowedOrigins,
  methods: ["GET", "POST"],
  credentials: true
}));

// ✅ Attach Socket.IO to HTTP server
const io = new Server(server, {
  cors: {
    origin: allowedOrigins,
    methods: ["GET", "POST"],
    credentials: true
  }
});

let robotSocket = null;

io.on("connection", (socket) => {
  console.log("Client connected:", socket.id);

  socket.on("register-robot", () => {
    console.log("Robot registered:", socket.id);
    robotSocket = socket;
    socket.broadcast.emit("robot-ready");
  });

  socket.on("offer", (data) => {
    if (robotSocket) {
      robotSocket.emit("offer", data);
    }
  });

  socket.on("answer", (data) => {
    socket.broadcast.emit("answer", data);
  });

  socket.on("candidate", (data) => {
    socket.broadcast.emit("candidate", data);
  });

  socket.on("disconnect", () => {
    if (socket === robotSocket) {
      robotSocket = null;
      io.emit("robot-disconnected");
    }
  });
});

// ✅ Start the server
server.listen(PORT, () => {
  console.log(`Signaling server running on http://localhost:${PORT}`);
});
