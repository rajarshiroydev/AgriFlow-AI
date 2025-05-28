import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import "./App.css";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
// import { GiFactory } from "react-icons/gi"; // REMOVED - No longer used directly here
import { ReactComponent as AgriFlowLogo } from "./assets/AgriFlowLogoText.svg"; // SVG Logo
import {
  FiMessageSquare,
  FiPlusCircle,
  FiMoreHorizontal,
  FiEdit2,
  FiTrash2,
  FiCheck,
  FiX,
} from "react-icons/fi";

// ... (rest of the App.js code from the previous "full code" response remains IDENTICAL)
// The only change is removing the GiFactory import line.
// The JSX for the sidebar header would be:
// <div className="sidebar-header">
//   <AgriFlowLogo className="sidebar-logo-svg" />
// </div>
// (No GiFactory icon here unless you explicitly add it back for a different purpose)

// For completeness, I'll paste the whole App.js again with just this one import line removed.

const API_URL =
  process.env.REACT_APP_API_URL || "http://localhost:8000/api/v1/chat";
const MAX_HISTORY_TURNS_FOR_API = 3;
const LOCAL_STORAGE_KEY = "agriflow_chat_sessions_v4";

const loadSessionsFromStorage = () => {
  try {
    const storedSessions = localStorage.getItem(LOCAL_STORAGE_KEY);
    return storedSessions ? JSON.parse(storedSessions) : [];
  } catch (error) {
    console.error("Error loading sessions from localStorage:", error);
    return [];
  }
};

const saveSessionsToStorage = (sessions) => {
  try {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(sessions));
  } catch (error) {
    console.error("Error saving sessions to localStorage:", error);
  }
};

const createInitialMessage = () => ({
  id: `initial-${Date.now()}`,
  sender: "ai",
  text: "Welcome! How can I help you analyze policies or supply chain data today?",
  type: "text",
});

function App() {
  const [currentMessages, setCurrentMessages] = useState(() => [
    createInitialMessage(),
  ]);
  const [savedSessions, setSavedSessions] = useState(() =>
    loadSessionsFromStorage()
  );
  const [activeChatId, setActiveChatId] = useState(null);
  const [isChatModified, setIsChatModified] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasInteracted, setHasInteracted] = useState(false);

  const [optionsMenuSessionId, setOptionsMenuSessionId] = useState(null);
  const [isRenamingSessionId, setIsRenamingSessionId] = useState(null);
  const [renameInputText, setRenameInputText] = useState("");
  const optionsMenuRef = useRef(null);
  const renameInputRef = useRef(null);

  useEffect(() => {
    saveSessionsToStorage(savedSessions);
  }, [savedSessions]);

  useEffect(() => {
    const initialMsgCount = currentMessages.filter((m) =>
      m.id.startsWith("initial-")
    ).length;
    if (
      currentMessages.length > initialMsgCount ||
      (initialMsgCount === 0 && currentMessages.length > 0)
    ) {
      const loadedSession = activeChatId
        ? savedSessions.find((s) => s.id === activeChatId)
        : null;
      if (loadedSession) {
        if (
          JSON.stringify(currentMessages) !==
          JSON.stringify(loadedSession.messages)
        ) {
          setIsChatModified(true);
        }
      } else if (currentMessages.length > initialMsgCount) {
        setIsChatModified(true);
      }
    }
  }, [currentMessages, activeChatId, savedSessions]);

  useEffect(() => {
    function handleClickOutside(event) {
      if (
        optionsMenuRef.current &&
        !optionsMenuRef.current.contains(event.target)
      ) {
        setOptionsMenuSessionId(null);
      }
    }
    if (optionsMenuSessionId) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [optionsMenuSessionId]);

  useEffect(() => {
    if (isRenamingSessionId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [isRenamingSessionId]);

  const generateChatTitle = (messagesForTitle) => {
    const firstUserMessage = messagesForTitle.find((m) => m.sender === "user");
    if (firstUserMessage && firstUserMessage.text) {
      const title =
        firstUserMessage.text.split(" ").slice(0, 5).join(" ") +
        (firstUserMessage.text.split(" ").length > 5 ? "..." : "");
      return title.trim().length > 0 ? title : "Chat Session";
    }
    return "New Chat";
  };
  const persistChat = useCallback((messagesToPersist, idOfChatToPersist) => {
    if (
      !messagesToPersist ||
      (messagesToPersist.length <= 1 &&
        messagesToPersist.some((m) => m.id.startsWith("initial-")) &&
        !messagesToPersist.some((m) => m.sender === "user"))
    ) {
      return idOfChatToPersist || null;
    }
    const title = generateChatTitle(messagesToPersist);
    const sessionId = idOfChatToPersist || `chat-${Date.now()}`;
    const sessionData = {
      id: sessionId,
      title: title,
      timestamp: Date.now(),
      messages: [...messagesToPersist],
    };
    setSavedSessions((prevSessions) => {
      const existingIndex = prevSessions.findIndex((s) => s.id === sessionId);
      let newSessions;
      if (existingIndex > -1) {
        newSessions = [...prevSessions];
        newSessions[existingIndex] = sessionData;
      } else {
        newSessions = [sessionData, ...prevSessions];
      }
      return newSessions.sort((a, b) => b.timestamp - a.timestamp);
    });
    setIsChatModified(false);
    return sessionId;
  }, []);
  const handleNewChat = useCallback(() => {
    if (isChatModified) {
      persistChat(currentMessages, activeChatId);
    }
    setCurrentMessages([createInitialMessage()]);
    setActiveChatId(null);
    setIsChatModified(false);
    if (!hasInteracted) setHasInteracted(true);
    setError(null);
  }, [
    isChatModified,
    currentMessages,
    activeChatId,
    persistChat,
    hasInteracted,
  ]);
  const handleLoadChat = useCallback(
    (sessionIdToLoad) => {
      if (
        isRenamingSessionId === sessionIdToLoad ||
        activeChatId === sessionIdToLoad
      )
        return;
      if (isChatModified) {
        persistChat(currentMessages, activeChatId);
      }
      const session = savedSessions.find((s) => s.id === sessionIdToLoad);
      if (session) {
        setCurrentMessages([...session.messages]);
        setActiveChatId(sessionIdToLoad);
        setIsChatModified(false);
        if (!hasInteracted) setHasInteracted(true);
        setError(null);
      }
    },
    [
      savedSessions,
      isChatModified,
      currentMessages,
      activeChatId,
      persistChat,
      hasInteracted,
      isRenamingSessionId,
    ]
  );
  const handleSendMessage = useCallback(
    async (inputText) => {
      if (!inputText.trim()) return;
      if (!hasInteracted) setHasInteracted(true);
      setError(null);
      const newUserMessage = {
        id: `user-${Date.now()}`,
        sender: "user",
        text: inputText,
        type: "text",
      };
      const tempCurrentMessages = [...currentMessages, newUserMessage];
      setCurrentMessages(tempCurrentMessages);
      setIsLoading(true);
      const messagesForApiHistory = tempCurrentMessages.slice(0, -1);
      const apiHistory = messagesForApiHistory
        .filter((m) => !m.id.startsWith("initial-"))
        .slice(-(MAX_HISTORY_TURNS_FOR_API * 2))
        .map((msg) => ({ sender: msg.sender, text: msg.text }));
      try {
        const payload = {
          query: inputText,
          user_id: "react_ui_user",
          history: apiHistory.length > 0 ? apiHistory : null,
        };
        const response = await axios.post(API_URL, payload, {
          timeout: 180000,
        });
        const aiResponseData = response.data;
        const newAiMessage = {
          id: `ai-${Date.now()}`,
          sender: "ai",
          text: aiResponseData.answer || "No answer found.",
          type: aiResponseData.error ? "error" : "text",
          sources: aiResponseData.sources || [],
          sql: aiResponseData.generated_sql,
          queryTypeDebug: aiResponseData.query_type_debug,
        };
        setCurrentMessages((prevMessages) => {
          const finalMessages = [...prevMessages, newAiMessage];
          const newActiveChatId = persistChat(finalMessages, activeChatId);
          if (!activeChatId && newActiveChatId) {
            setActiveChatId(newActiveChatId);
          }
          return finalMessages;
        });
      } catch (err) {
        console.error("API Error:", err);
        let emc = "Sorry, an error occurred.";
        if (err.response) {
          emc = `Error: ${
            err.response.data.detail ||
            err.response.statusText ||
            "Server error"
          }`;
        } else if (err.request) {
          emc = "Network error or no response.";
        } else {
          emc = `Error: ${err.message}`;
        }
        setError(emc);
        const errorAiMsg = {
          id: `error-${Date.now()}`,
          sender: "ai",
          text: emc,
          type: "error",
        };
        setCurrentMessages((prev) => [...prev, errorAiMsg]);
      } finally {
        setIsLoading(false);
      }
    },
    [currentMessages, activeChatId, hasInteracted, persistChat]
  );
  const getCategorizedSessions = () => {
    const today = [];
    const yesterday = [];
    const older = [];
    const now = new Date();
    const todayStart = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate()
    ).getTime();
    const yesterdayStart = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() - 1
    ).getTime();
    const sessionsToCategorize = [...savedSessions];
    sessionsToCategorize.sort((a, b) => b.timestamp - a.timestamp);
    sessionsToCategorize.forEach((session) => {
      if (session.timestamp >= todayStart) today.push(session);
      else if (session.timestamp >= yesterdayStart) yesterday.push(session);
      else older.push(session);
    });
    return { today, yesterday, older };
  };
  const categorizedSessions = getCategorizedSessions();
  const handleDeleteChat = (sessionIdToDelete) => {
    setOptionsMenuSessionId(null);
    setSavedSessions((prev) =>
      prev.filter((session) => session.id !== sessionIdToDelete)
    );
    if (activeChatId === sessionIdToDelete) {
      setCurrentMessages([createInitialMessage()]);
      setActiveChatId(null);
      setIsChatModified(false);
    }
  };
  const handleStartRename = (session) => {
    setIsRenamingSessionId(session.id);
    setRenameInputText(session.title);
    setOptionsMenuSessionId(null);
  };
  const handleConfirmRename = (sessionIdToRename) => {
    const trimmedTitle = renameInputText.trim();
    if (!trimmedTitle) {
      const originalSession = savedSessions.find(
        (s) => s.id === sessionIdToRename
      );
      setRenameInputText(originalSession?.title || "Chat Session");
      setIsRenamingSessionId(null);
      return;
    }
    setSavedSessions((prev) =>
      prev
        .map((session) =>
          session.id === sessionIdToRename
            ? { ...session, title: trimmedTitle, timestamp: Date.now() }
            : session
        )
        .sort((a, b) => b.timestamp - a.timestamp)
    );
    setIsRenamingSessionId(null);
    setRenameInputText("");
  };
  const handleCancelRename = () => {
    setIsRenamingSessionId(null);
    setRenameInputText("");
  };
  const toggleOptionsMenu = (e, sessionId) => {
    e.stopPropagation();
    setOptionsMenuSessionId((prevId) =>
      prevId === sessionId ? null : sessionId
    );
    setIsRenamingSessionId(null);
  };

  return (
    <div
      className={`App ${
        hasInteracted ? "chat-view-active" : "landing-view-active"
      }`}
    >
      <aside className={`sidebar ${hasInteracted ? "visible" : ""}`}>
        <div className="sidebar-header">
          <AgriFlowLogo className="sidebar-logo-svg" />
        </div>
        <button className="new-chat-button" onClick={handleNewChat}>
          {" "}
          <FiPlusCircle size={16} /> New Chat{" "}
        </button>
        {savedSessions.length > 0 && (
          <>
            {Object.entries(categorizedSessions).map(
              ([categoryName, sessionsInCategory]) =>
                sessionsInCategory.length > 0 && (
                  <div className="history-section" key={categoryName}>
                    <h3>
                      {categoryName.charAt(0).toUpperCase() +
                        categoryName.slice(1)}
                    </h3>
                    <ul>
                      {sessionsInCategory.map((session) => (
                        <li
                          key={session.id}
                          onClick={() => {
                            if (isRenamingSessionId !== session.id)
                              handleLoadChat(session.id);
                          }}
                          className={`${
                            activeChatId === session.id
                              ? "active-chat-history"
                              : ""
                          } ${
                            isRenamingSessionId === session.id
                              ? "renaming-active"
                              : ""
                          } ${
                            optionsMenuSessionId === session.id
                              ? "options-menu-active"
                              : ""
                          }`}
                        >
                          {isRenamingSessionId === session.id ? (
                            <div className="rename-input-container">
                              {" "}
                              <input
                                ref={renameInputRef}
                                type="text"
                                value={renameInputText}
                                onChange={(e) =>
                                  setRenameInputText(e.target.value)
                                }
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    e.preventDefault();
                                    handleConfirmRename(session.id);
                                  }
                                  if (e.key === "Escape") handleCancelRename();
                                }}
                                onBlur={() => {
                                  if (renameInputText.trim()) {
                                    handleConfirmRename(session.id);
                                  } else {
                                    handleCancelRename();
                                  }
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />{" "}
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleConfirmRename(session.id);
                                }}
                                className="rename-action-button confirm"
                              >
                                <FiCheck />
                              </button>{" "}
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleCancelRename();
                                }}
                                className="rename-action-button cancel"
                              >
                                <FiX />
                              </button>{" "}
                            </div>
                          ) : (
                            <>
                              {" "}
                              <FiMessageSquare size={14} />{" "}
                              <span className="session-title-text">
                                {session.title}
                              </span>{" "}
                              <button
                                className="options-button"
                                onClick={(e) =>
                                  toggleOptionsMenu(e, session.id)
                                }
                                aria-label="Chat options"
                              >
                                {" "}
                                <FiMoreHorizontal />{" "}
                              </button>{" "}
                              {optionsMenuSessionId === session.id && (
                                <div
                                  className="options-menu"
                                  ref={optionsMenuRef}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {" "}
                                  <button
                                    onClick={() => handleStartRename(session)}
                                  >
                                    <FiEdit2 /> Rename
                                  </button>{" "}
                                  <button
                                    onClick={() => handleDeleteChat(session.id)}
                                    className="delete-option"
                                  >
                                    <FiTrash2 /> Delete
                                  </button>{" "}
                                </div>
                              )}{" "}
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )
            )}
          </>
        )}
      </aside>

      <main
        className={`main-content ${
          hasInteracted ? "chat-mode" : "landing-mode"
        }`}
      >
        {!hasInteracted && (
          <div className="landing-content">
            <AgriFlowLogo className="landing-logo-svg" />
            <p className="landing-description">
              {" "}
              Unlock intelligent insights from your agricultural policies and
              supply chain data. AgriFlow.ai helps you make smarter, data-driven
              decisions to optimize operations and navigate complex guidelines
              with ease.{" "}
            </p>
            <p className="landing-prompt">How can I help you today?</p>
            <div className="chat-input-container">
              {" "}
              {error && <div className="app-error-banner">{error}</div>}{" "}
              <ChatInput
                onSendMessage={handleSendMessage}
                isLoading={isLoading}
              />{" "}
            </div>
          </div>
        )}
        {hasInteracted && (
          <>
            <div className="chat-window-container">
              {" "}
              <ChatWindow messages={currentMessages} />{" "}
            </div>
            <div className="chat-input-container">
              {" "}
              {error && <div className="app-error-banner">{error}</div>}{" "}
              <ChatInput
                onSendMessage={handleSendMessage}
                isLoading={isLoading}
              />{" "}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
