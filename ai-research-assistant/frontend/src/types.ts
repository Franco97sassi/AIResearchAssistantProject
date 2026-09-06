export type UploadResponse = {
  message: string;
  filename: string;
  stored_filename: string;
  size_bytes: number;
  page_count: number;
  character_count: number;
  extraction_method: string;
  ocr_attempted: boolean;
  ocr_available: boolean;
  text_preview: string;
  document_id: string;
  chunks_indexed: number;
  collection_name: string;
};

export type Source = {
  text: string;
  filename: string;
  page_number: number;
  document_id: string;
  distance: number | null;
};

export type SearchResponse = {
  question: string;
  results: Source[];
};

export type AgentStep = {
  name: string;
  description: string;
  tool: string | null;
  decision: string | null;
  role?: string | null;
};

export type ChatHistoryMessage = {
  id: string;
  question: string;
  answer: string;
  model: string;
  used_llm: boolean;
  sources: Source[];
  agent_steps?: AgentStep[];
  created_at: string;
};

export type ChatMessage = {
  id: string;
  question: string;
  answer: string;
  model: string;
  usedLlm: boolean;
  sources: Source[];
  agentSteps: AgentStep[];
  createdAt: string;
};

export type ChatResponse = {
  session_id: string;
  question: string;
  answer: string;
  model: string;
  used_llm: boolean;
  sources: Source[];
  agent_steps?: AgentStep[];
  agent_framework?: string;
  history: ChatHistoryMessage[];
};

export type ChatSessionResponse = {
  session_id: string;
  created_at: string;
  updated_at: string;
  messages: ChatHistoryMessage[];
};

export type SessionSummary = {
  session_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_question: string;
};

export type AiTopicsResponse = {
  free_first: boolean;
  covered: string[];
  intentionally_excluded_paid_model_apis: string[];
  next_steps: string[];
};

export type MetricsResponse = {
  event_count: number;
  average_latency_ms: number;
  total_estimated_tokens: number;
  average_source_count: number;
};

export type EvaluationResponse = {
  faithfulness: number;
  context_precision: number;
  context_recall_proxy: number;
  hallucination_risk: string;
  grounded: boolean;
  source_coverage: number;
  estimated_answer_tokens: number;
  notes: string[];
};

export type ChatMode = 'rag' | 'agent' | 'stream';
