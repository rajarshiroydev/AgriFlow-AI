import React from "react";
import "./ChatMessage.css";
import { FaUserCircle, FaRobot } from "react-icons/fa";

const parseSimpleMarkdown = (text) => {
  if (typeof text !== "string") {
    return text === null || typeof text === "undefined"
      ? "\u00A0"
      : String(text);
  }
  const parts = text.split(/(\*\*.*?\*\*)/g);
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

  const messageTextContent =
    typeof message.text === "string" ? message.text : "";
  const messageSources =
    message && Array.isArray(message.sources) ? message.sources : [];
  const messageSql =
    message && typeof message.sql === "string" ? message.sql : null;
  const queryTypeDebug =
    message && typeof message.queryTypeDebug === "string"
      ? message.queryTypeDebug
      : null;

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
        <div className="message-text">
          {parseSimpleMarkdown(messageTextContent)}
        </div>
        {messageSources.length > 0 && (
          <div className="message-extras sources-container">
            <span className="extra-title">Sources:</span>
            <ul>
              {messageSources.map((source, index) => (
                <li key={index}>{source}</li>
              ))}
            </ul>
          </div>
        )}
        {messageSql &&
          messageSql !== "NO_QUERY_POSSIBLE" &&
          messageSql !== "Not applicable (no DB question)." &&
          messageSql !== "SQL_EXTRACTION_FAILED_NO_RAW_SQLQUERY_TEXT_FOUND" && (
            <div className="message-extras sql-container">
              <span className="extra-title">Generated SQL:</span>
              <pre className="sql-code">
                <code>{messageSql}</code>
              </pre>
            </div>
          )}
        {queryTypeDebug && (
          <div className="message-extras query-type-container">
            <span className="extra-title">Query Type (Debug):</span>{" "}
            {queryTypeDebug}
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
