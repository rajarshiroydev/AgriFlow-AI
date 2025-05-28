// components/ChatInput.js (Assumed structure)
import React, { useState } from "react";
import "./ChatInput.css";
import { FiSend } from "react-icons/fi";

function ChatInput({ onSendMessage, isLoading }) {
  const [inputValue, setInputValue] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (inputValue.trim() && !isLoading) {
      onSendMessage(inputValue);
      setInputValue("");
    }
  };

  return (
    <form className="chat-input-form" onSubmit={handleSubmit}>
      <input
        type="text"
        className="chat-text-input" // We will style this
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        placeholder="Ask about policies or supply chain data..."
        disabled={isLoading}
      />
      <button
        type="submit"
        className="chat-send-button"
        disabled={isLoading || !inputValue.trim()}
      >
        <FiSend size={20} />
      </button>
    </form>
  );
}
export default ChatInput;
