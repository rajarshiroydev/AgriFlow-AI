import React, { useState } from "react";
import "./ChatInput.css";
import { FiSend } from "react-icons/fi"; // Send icon

function ChatInput({ onSendMessage, isLoading }) {
  const [inputValue, setInputValue] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (inputValue.trim() && !isLoading) {
      onSendMessage(inputValue);
      setInputValue("");
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      // Send on Enter, allow Shift+Enter for newline
      e.preventDefault(); // Prevent default newline in input
      handleSubmit(e);
    }
  };

  return (
    <div className="chat-input-container">
      <form onSubmit={handleSubmit} className="chat-input-form">
        <textarea
          className="chat-input-field"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask about policies or supply chain data..."
          disabled={isLoading}
          rows="1" // Start with 1 row, will expand
        />
        <button
          type="submit"
          className="chat-input-button"
          disabled={isLoading}
          title="Send message"
        >
          {isLoading ? <div className="spinner"></div> : <FiSend size={20} />}
        </button>
      </form>
    </div>
  );
}

export default ChatInput;
