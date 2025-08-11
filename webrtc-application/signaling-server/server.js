const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const cors = require("cors");

const app = express();
const server = http.createServer(app);

const PORT = process.env.PORT || 9010;

const allowedOrigins = [
  "http://localhost:5500",
  // "http://127.0.0.1:5500",
  // "http://localhost:3000",
  // "https://application-8mai.onrender.com",
  "https://incredible-rugelach-0de508.netlify.app"
];

app.use(
  cors({
    origin: allowedOrigins,
    methods: ["GET", "POST"],
    credentials: true,
  })
);

const io = new Server(server, {
  cors: {
    origin: allowedOrigins,
    methods: ["GET", "POST"],
    credentials: true,
  },
});

let robotSocket = null;
let frontendSocket = null;

io.on("connection", (socket) => {
  console.log("Client connected:", socket.id);

  socket.on("register-robot", () => {
    if (robotSocket) {
      console.log("Robot connection already connected:", socket.id);
      socket.emit("connection-error", "Robot already connected");
      socket.disconnect(true);
      return;
    }
    robotSocket = socket;
    console.log("Robot connected:", socket.id);
    socket.emit("connection-accepted", "Robot connection established", { role: "robot" });

  
    if (frontendSocket) {
      frontendSocket.emit("robot-ready");
      robotSocket.emit("frontend-ready");
    }
  });

  socket.on("register-frontend", () => {
    if (frontendSocket) {
      console.log("Frontend connection already connected:", socket.id);
      socket.emit("connection-error", "Frontend already connected");
      socket.disconnect(true);
      return;
    }
    frontendSocket = socket;
    console.log("Frontend connected:", socket.id);
    socket.emit("connection-accepted", "Frontend connection established", { role: "frontend" });

  
    if (robotSocket) {
      frontendSocket.emit("robot-ready");
      robotSocket.emit("frontend-ready");
    }
  });

  socket.on("offer", (data) => {
    if (socket === frontendSocket && robotSocket) {
      robotSocket.emit("offer", data);
    } else {
      socket.emit("connection-error", { message: "Robot not connected or you are not frontend" });
    }
  });

  socket.on("answer", (data) => {
    if (socket === robotSocket && frontendSocket) {
      frontendSocket.emit("answer", data);
    } else {
      socket.emit("connection-error", { message: "Frontend not connected or you are not robot" });
    }
  });

  socket.on("candidate", (data) => {
    if (socket === robotSocket && frontendSocket) {
      frontendSocket.emit("candidate", data);
    } else if (socket === frontendSocket && robotSocket) {
      robotSocket.emit("candidate", data);
    } else {
      socket.emit("connection-error", { message: "Peer not connected or invalid sender" });
    }
  });

  socket.on("disconnect", () => {
    console.log("Client disconnected:", socket.id);
    if (socket === robotSocket) {
      robotSocket = null;
      if (frontendSocket) {
        frontendSocket.emit("robot-disconnected");
      }
    } else if (socket === frontendSocket) {
      frontendSocket = null;
      if (robotSocket) {
        robotSocket.emit("frontend-disconnected");
      }
    }
  });
});


server.listen(PORT, () => {
  console.log(`Signaling server running on http://localhost:${PORT}`);
});
