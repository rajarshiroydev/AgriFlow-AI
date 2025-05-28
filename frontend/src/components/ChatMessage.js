import React from "react";
import "./ChatMessage.css";
import { FaUserCircle, FaRobot } from "react-icons/fa"; // User and AI icons
// import { VscSourceControl } from 'react-icons/vsc'; // Icon for sources
// import { FiDatabase } from 'react-icons/fi'; // Icon for SQL

// A simple Markdown-like parser for bold text (e.g., **text**)
// For more complex markdown, consider using a library like 'react-markdown'
const parseSimpleMarkdown = (text) => {
  if (typeof text !== "string") {
    return text; // Or handle appropriately, e.g., return an empty string or a placeholder
  }
  const parts = text.split(/(\*\*.*?\*\*)/g); // Split by **bolded** text
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
};

function ChatMessage({ message }) {
  const isUser = message.sender === "user";
  const isError = message.type === "error";

  return (
    <div
      className={`chat-message ${isUser ? "user-message" : "ai-message"} ${
        isError ? "error-message-bubble" : ""
      }`}
    >
      <div className="message-avatar">
        {isUser ? <FaUserCircle size={28} /> : <FaRobot size={28} />}
      </div>
      <div className="message-content">
        <div className="message-text">{parseSimpleMarkdown(message.text)}</div>
        {message.sources && message.sources.length > 0 && (
          <div className="message-extras sources-container">
            <span className="extra-title">Sources:</span>
            <ul>
              {message.sources.map((source, index) => (
                <li key={index}>{source}</li>
              ))}
            </ul>
          </div>
        )}
        {message.sql &&
          message.sql !== "NO_QUERY_POSSIBLE" &&
          message.sql !== "Not applicable (no DB question)." &&
          message.sql !==
            "SQL_EXTRACTION_FAILED_NO_RAW_SQLQUERY_TEXT_FOUND" && (
            <div className="message-extras sql-container">
              <span className="extra-title">Generated SQL:</span>
              <pre className="sql-code">
                <code>{message.sql}</code>
              </pre>
            </div>
          )}
        {/* You could add queryType debug info here if desired for the demo */}
        {/* {message.queryType && (
          <div className="message-extras query-type-container">
            <span className="extra-title">Query Type (Debug):</span> {message.queryType}
          </div>
        )} */}
      </div>
    </div>
  );
}

export default ChatMessage;
