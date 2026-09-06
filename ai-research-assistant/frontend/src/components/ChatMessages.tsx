import { formatDate } from '../lib/format';
import type { ChatMessage } from '../types';
import { SourceList } from './SourceList';

export function ChatMessages({ messages }: { messages: ChatMessage[] }) {
  if (messages.length === 0) {
    return (
      <div className="empty-state">
        <strong>Listo para la demo.</strong>
        <span>Sube un PDF y pregunta sobre su contenido.</span>
      </div>
    );
  }

  return messages.map((message) => (
    <section className="message" key={message.id}>
      <p className="question">{message.question}</p>
      <p className="answer">{message.answer}</p>
      <div className="message-meta">
        <span>Modelo: {message.model}</span>
        <span>{message.usedLlm ? 'LLM activo' : 'Fallback local'}</span>
        <span>{formatDate(message.createdAt)}</span>
      </div>
      {message.agentSteps.length > 0 && (
        <details className="agent-steps">
          <summary>Pasos del agente</summary>
          <ol>
            {message.agentSteps.map((step, index) => (
              <li key={`${message.id}-${step.name}-${index}`}>
                <strong>{step.name}{step.role ? ` · ${step.role}` : ''}</strong>
                <span>{step.description}</span>
                {(step.tool || step.decision) && (
                  <small>
                    {step.tool ? `Herramienta: ${step.tool}` : ''}
                    {step.tool && step.decision ? ' · ' : ''}
                    {step.decision ? `Decisión: ${step.decision}` : ''}
                  </small>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
      {message.sources.length > 0 && (
        <details className="sources-panel" open>
          <summary>Fuentes recuperadas</summary>
          <SourceList sources={message.sources} />
        </details>
      )}
    </section>
  ));
}
