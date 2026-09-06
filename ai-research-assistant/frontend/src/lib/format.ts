import type { ChatHistoryMessage, ChatMessage } from '../types';

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

export function formatDate(value: string): string {
  if (!value) return 'Sin fecha';
  return new Date(value).toLocaleString();
}

export function formatDistance(value: number | null): string {
  if (value === null) return 'Sin distancia';
  return value.toFixed(4);
}

export function mapHistoryMessage(message: ChatHistoryMessage): ChatMessage {
  return {
    id: message.id,
    question: message.question,
    answer: message.answer,
    model: message.model,
    usedLlm: message.used_llm,
    sources: message.sources,
    agentSteps: message.agent_steps ?? [],
    createdAt: message.created_at,
  };
}
