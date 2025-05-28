import React from "react";
import "./ChatMessage.css";
import { FaUserCircle, FaRobot } from "react-icons/fa";
import { FiCopy } from "react-icons/fi";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import { darcula } from "react-syntax-highlighter/dist/esm/styles/prism"; // Using darcula

SyntaxHighlighter.registerLanguage("sql", sql);

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

const formatSQLForDisplay = (sqlString) => {
  if (!sqlString || typeof sqlString !== "string") return sqlString;
  const keywords = [
    "SELECT",
    "FROM",
    "WHERE",
    "LEFT JOIN",
    "RIGHT JOIN",
    "INNER JOIN",
    "JOIN",
    "ON",
    "GROUP BY",
    "ORDER BY",
    "LIMIT",
    "OFFSET",
    "HAVING",
    "UNION",
    "VALUES",
    "INSERT INTO",
    "UPDATE",
    "DELETE FROM",
    "WITH",
  ];
  let formattedSQL = sqlString;
  keywords.forEach((keyword) => {
    const regex = new RegExp(`\\b(${keyword})\\b`, "gi");
    formattedSQL = formattedSQL.replace(regex, "\n$1");
  });
  formattedSQL = formattedSQL.trimStart();
  return formattedSQL;
};

function ChatMessage({ message }) {
  const isUser = message.sender === "user";
  const isError = message.type === "error";

  const messageTextContent =
    typeof message.text === "string" ? message.text : "";
  const messageSources =
    message && Array.isArray(message.sources) ? message.sources : [];
  const rawSql =
    message && typeof message.sql === "string" ? message.sql : null;
  const queryTypeDebug =
    message && typeof message.queryTypeDebug === "string"
      ? message.queryTypeDebug
      : null;

  const displaySql = rawSql ? formatSQLForDisplay(rawSql) : null;

  const handleCopySql = () => {
    if (rawSql) {
      navigator.clipboard
        .writeText(rawSql)
        .then(() => {
          alert("SQL Copied to clipboard!");
        })
        .catch((err) => {
          console.error("Failed to copy SQL: ", err);
          alert("Failed to copy SQL.");
        });
    }
  };

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
        {displaySql &&
          rawSql !== "NO_QUERY_POSSIBLE" &&
          rawSql !== "Not applicable (no DB question)." &&
          rawSql !== "SQL_EXTRACTION_FAILED_NO_RAW_SQLQUERY_TEXT_FOUND" && (
            <div className="message-extras sql-container">
              <div className="sql-header">
                <span className="extra-title">Generated SQL:</span>
                <button
                  onClick={handleCopySql}
                  className="copy-sql-button"
                  title="Copy SQL"
                >
                  <FiCopy />
                </button>
              </div>
              <div className="sql-code-block-wrapper">
                <SyntaxHighlighter
                  language="sql"
                  style={darcula} // Apply the darcula theme
                  customStyle={{
                    margin: 0,
                    fontSize: "0.85em",
                    // Darcula provides its own background and padding for the <pre> tag.
                    // If you want to override its padding: padding: '1em',
                  }}
                  codeTagProps={{
                    style: {
                      fontFamily: "Consolas, 'Courier New', monospace",
                    },
                  }}
                  wrapLongLines={true}
                >
                  {String(displaySql || "")}
                </SyntaxHighlighter>
              </div>
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
