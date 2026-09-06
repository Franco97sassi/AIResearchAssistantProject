import { useState } from 'react';

export const SESSION_STORAGE_KEY = 'ai-research-assistant-session-id';

function createSessionId(): string {
  return crypto.randomUUID();
}

function getInitialSessionId(): string {
  const storedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
  if (storedSessionId) return storedSessionId;
  const sessionId = createSessionId();
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}

export function usePersistentSession() {
  const [sessionId, setSessionState] = useState(getInitialSessionId);

  function selectSession(nextSessionId: string) {
    localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
    setSessionState(nextSessionId);
  }

  function createSession() {
    const sessionId = createSessionId();
    selectSession(sessionId);
    return sessionId;
  }

  return { sessionId, selectSession, createSession };
}
