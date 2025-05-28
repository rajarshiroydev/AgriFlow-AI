import React, { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage";
import "./ChatWindow.css";

function ChatWindow({ messages }) {
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]); // Scroll whenever messages update

  return (
    <div className="chat-window">
      {messages.map((msg) => (
        <ChatMessage key={msg.id} message={msg} />
      ))}
      <div ref={messagesEndRef} /> {/* Invisible element to scroll to */}
    </div>
  );
}

export default ChatWindow;
