import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import "./App.css"; // Main CSS
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import { ReactComponent as AgriFlowLogo } from "./assets/AgriFlowLogoText.svg";
import {
  FiMessageSquare,
  FiPlusCircle,
  FiMoreHorizontal,
  FiEdit2,
  FiTrash2,
  FiCheck,
  FiX,
  FiUserCheck, // Assuming you'll re-add user profile selector
} from "react-icons/fi";

const API_URL =
  process.env.REACT_APP_API_URL || "http://localhost:8000/api/v1/chat";
const MAX_HISTORY_TURNS_FOR_API = 3;
const LOCAL_STORAGE_KEY = "agriflow_chat_sessions_v4"; // Keep or increment if structure changes

// --- User Profile Section ---
const SIMULATED_USER_PROFILES = {
  guest_global: {
    name: "Guest (Global)",
    description: "Access to public policies only.",
  },
  analyst_us: {
    name: "Analyst (US)",
    description: "US sales & inventory data.",
  },
  manager_emea: {
    name: "Manager (EMEA)",
    description: "EMEA sales, inventory, financials.",
  },
  admin_global: {
    name: "Administrator (Global)",
    description: "Full access to all data & regions.",
  },
};
const DEFAULT_SIMULATED_USER_ID = "guest_global";
// --- End User Profile Section ---

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
  const [simulatedUserId, setSimulatedUserId] = useState(
    DEFAULT_SIMULATED_USER_ID
  ); // For user profile selection

  const optionsMenuRef = useRef(null);
  const renameInputRef = useRef(null);

  // console.log("App.js - Render - hasInteracted:", hasInteracted, "activeChatId:", activeChatId);

  useEffect(() => {
    saveSessionsToStorage(savedSessions);
  }, [savedSessions]);

  useEffect(() => {
    const initialMsgCount = currentMessages.filter((m) =>
      m.id.startsWith("initial-")
    ).length;
    let modified = false;
    if (currentMessages.length > initialMsgCount) {
      if (activeChatId) {
        const loadedSession = savedSessions.find((s) => s.id === activeChatId);
        if (
          loadedSession &&
          JSON.stringify(currentMessages) !==
            JSON.stringify(loadedSession.messages)
        )
          modified = true;
      } else {
        modified = true;
      }
    }
    setIsChatModified(modified);
  }, [currentMessages, activeChatId, savedSessions]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        optionsMenuRef.current &&
        !optionsMenuRef.current.contains(event.target)
      )
        setOptionsMenuSessionId(null);
    };
    if (optionsMenuSessionId)
      document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [optionsMenuSessionId]);

  useEffect(() => {
    if (isRenamingSessionId && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [isRenamingSessionId]);

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
      title,
      timestamp: Date.now(),
      messages: [...messagesToPersist],
    };
    setSavedSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === sessionId);
      const newSessions = idx > -1 ? [...prev] : [sessionData, ...prev];
      if (idx > -1) newSessions[idx] = sessionData;
      return newSessions.sort((a, b) => b.timestamp - a.timestamp);
    });
    setIsChatModified(false);
    return sessionId;
  }, []); // generateChatTitle is stable, setIsChatModified & setSavedSessions are stable setters

  const handleInteractionStart = useCallback(() => {
    if (!hasInteracted) {
      // console.log("Setting hasInteracted to true via handleInteractionStart");
      setHasInteracted(true);
    }
  }, [hasInteracted]);

  const handleNewChat = useCallback(() => {
    handleInteractionStart();
    if (isChatModified) persistChat(currentMessages, activeChatId);
    setCurrentMessages([createInitialMessage()]);
    setActiveChatId(null);
    setIsChatModified(false);
    setError(null);
  }, [
    isChatModified,
    currentMessages,
    activeChatId,
    persistChat,
    handleInteractionStart,
  ]);

  const handleLoadChat = useCallback(
    (sessionIdToLoad) => {
      handleInteractionStart();
      if (
        isRenamingSessionId === sessionIdToLoad ||
        activeChatId === sessionIdToLoad
      )
        return;
      if (isChatModified) persistChat(currentMessages, activeChatId);
      const session = savedSessions.find((s) => s.id === sessionIdToLoad);
      if (session) {
        setCurrentMessages([...session.messages]);
        setActiveChatId(sessionIdToLoad);
        setIsChatModified(false);
        setError(null);
      }
    },
    [
      savedSessions,
      isChatModified,
      currentMessages,
      activeChatId,
      persistChat,
      handleInteractionStart,
      isRenamingSessionId,
    ]
  );

  const handleSendMessage = useCallback(
    async (inputText) => {
      if (!inputText.trim()) return;
      handleInteractionStart();
      setError(null);
      const newUserMessage = {
        id: `user-${Date.now()}`,
        sender: "user",
        text: inputText,
        type: "text",
      };
      const messagesWithUser = [...currentMessages, newUserMessage];
      setCurrentMessages(messagesWithUser);
      setIsLoading(true);

      const apiHistory = messagesWithUser
        .filter((m) => !m.id.startsWith("initial-"))
        .slice(0, -1)
        .slice(-(MAX_HISTORY_TURNS_FOR_API * 2))
        .map((msg) => ({ sender: msg.sender, text: msg.text }));
      try {
        const payload = {
          query: inputText,
          user_id: simulatedUserId,
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

        setCurrentMessages((prevMsgs) => {
          const finalMessages = [...prevMsgs, newAiMessage];
          const newOrUpdatedChatId = persistChat(finalMessages, activeChatId);
          if (!activeChatId && newOrUpdatedChatId)
            setActiveChatId(newOrUpdatedChatId);
          return finalMessages;
        });
      } catch (err) {
        console.error("API Error:", err);
        let emc = "An error occurred.";
        if (err.response)
          emc = `Error: ${
            err.response.data.detail ||
            err.response.statusText ||
            "Server error"
          }`;
        else if (err.request) emc = "Network error or no response.";
        else emc = `Error: ${err.message}`;
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
    [
      currentMessages,
      activeChatId,
      persistChat,
      handleInteractionStart,
      simulatedUserId,
    ]
  ); // Added simulatedUserId

  const getCategorizedSessions = () => {
    const today = [],
      yesterday = [],
      older = [];
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
    [...savedSessions]
      .sort((a, b) => b.timestamp - a.timestamp)
      .forEach((session) => {
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
      setIsRenamingSessionId(null);
      return;
    }
    setSavedSessions((prev) =>
      prev
        .map((s) =>
          s.id === sessionIdToRename
            ? { ...s, title: trimmedTitle, timestamp: Date.now() }
            : s
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

  const handleUserChange = (newUserId) => {
    if (newUserId !== simulatedUserId) {
      if (
        isChatModified &&
        (currentMessages.length > 1 ||
          currentMessages.some(
            (m) => m.sender === "user" && !m.id.startsWith("initial-")
          ))
      ) {
        persistChat(currentMessages, activeChatId);
      }
      setSimulatedUserId(newUserId);
      setCurrentMessages([createInitialMessage()]);
      setActiveChatId(null);
      setIsChatModified(false);
      if (!hasInteracted) handleInteractionStart();
      setError(null);
      setOptionsMenuSessionId(null);
      setIsRenamingSessionId(null);
    }
  };

  return (
    <div
      className={`App ${
        hasInteracted ? "chat-view-active" : "landing-view-active"
      }`}
    >
      <aside className="sidebar">
        {" "}
        {/* Class only "sidebar", visibility controlled by parent */}
        <div className="sidebar-header">
          <AgriFlowLogo className="sidebar-logo-svg" />
        </div>
        <div className="user-profile-selector history-section">
          <h3>
            <FiUserCheck /> Acting as:
          </h3>
          <select
            value={simulatedUserId}
            onChange={(e) => handleUserChange(e.target.value)}
            className="profile-select-dropdown"
          >
            {Object.entries(SIMULATED_USER_PROFILES).map(([id, profile]) => (
              <option key={id} value={id}>
                {profile.name}
              </option>
            ))}
          </select>
          {SIMULATED_USER_PROFILES[simulatedUserId] && (
            <p className="profile-description">
              {SIMULATED_USER_PROFILES[simulatedUserId].description}
            </p>
          )}
        </div>
        <button className="new-chat-button" onClick={handleNewChat}>
          <FiPlusCircle size={16} /> New Chat
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
                              />
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleConfirmRename(session.id);
                                }}
                                className="rename-action-button confirm"
                              >
                                <FiCheck />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleCancelRename();
                                }}
                                className="rename-action-button cancel"
                              >
                                <FiX />
                              </button>
                            </div>
                          ) : (
                            <>
                              <FiMessageSquare size={14} />
                              <span className="session-title-text">
                                {session.title}
                              </span>
                              <button
                                className="options-button"
                                onClick={(e) =>
                                  toggleOptionsMenu(e, session.id)
                                }
                                aria-label="Chat options"
                              >
                                <FiMoreHorizontal />
                              </button>
                              {optionsMenuSessionId === session.id && (
                                <div
                                  className="options-menu"
                                  ref={optionsMenuRef}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <button
                                    onClick={() => handleStartRename(session)}
                                  >
                                    <FiEdit2 /> Rename
                                  </button>
                                  <button
                                    onClick={() => handleDeleteChat(session.id)}
                                    className="delete-option"
                                  >
                                    <FiTrash2 /> Delete
                                  </button>
                                </div>
                              )}
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
              Unlock intelligent insights from your agricultural policies and
              supply chain data. AgriFlow.ai helps you make smarter, data-driven
              decisions to optimize operations and navigate complex guidelines
              with ease.
            </p>
            <p className="landing-prompt">How can I help you today?</p>
            <div className="chat-input-container">
              {error && <div className="app-error-banner">{error}</div>}
              <ChatInput
                onSendMessage={handleSendMessage}
                isLoading={isLoading}
              />
            </div>
          </div>
        )}
        {hasInteracted && (
          <>
            <div className="chat-window-container">
              <ChatWindow messages={currentMessages} />
            </div>
            <div className="chat-input-container">
              {error && <div className="app-error-banner">{error}</div>}
              <ChatInput
                onSendMessage={handleSendMessage}
                isLoading={isLoading}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
export default App;
