/**
 * Custom hook for streaming chat with SSE (Server-Sent Events)
 * Implements token-by-token streaming with metadata completion
 */

import { useState, useRef, useCallback } from "react";
import { useSession } from "@/store/session";
import type { ChatMessage } from "@/lib/types";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8004";

interface SSETokenEvent {
  type: "token";
  text: string;
}

interface SSEMetadataEvent {
  type: "metadata";
  intent: string;
  sub_intent: string;
  confidence: number; // 0-100
  citations: Array<{
    source: string;
    source_ref?: string;
    source_type?: "code" | "docs" | "adrs" | "incidents" | "specs";
    reference?: string;
    chunk_text?: string;
    line_number?: number;
    score?: number;
    details?: string;
    relevance?: string;
  }>;
  source_breakdown: Record<string, number>;
  chain_steps: Array<string | {
    name?: string;
    step_name?: string;
    latency_ms?: number;
    tokens?: number;
    tokens_used?: number;
  }>;
  follow_up_suggestions: string[];
}

type SSEEvent = SSETokenEvent | SSEMetadataEvent;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function useStreamingChat() {
  const { activeRepo, authHeaders } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  
  // Use ref to avoid stale closures when appending tokens
  const contentRef = useRef("");
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const firstTokenTimeRef = useRef<number | null>(null);
  
  // Store the last user message for retry
  const lastUserMessageRef = useRef<string>("");
  const lastChannelRef = useRef<"web" | "cli">("web");

  const stopStreaming = useCallback(() => {
    if (readerRef.current) {
      readerRef.current.cancel();
      readerRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  const sendMessage = useCallback(
    async (text: string, channel: "web" | "cli" = "web") => {
      // Store for retry
      lastUserMessageRef.current = text;
      lastChannelRef.current = channel;
      
      // Add user message
      const userMsg: ChatMessage = {
        id: generateId(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // Add streaming assistant message
      const assistantMsgId = generateId();
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        streaming: true,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setIsStreaming(true);
      contentRef.current = "";
      firstTokenTimeRef.current = Date.now();

      try {
        const response = await fetch(`${BACKEND}/adapters/web/ask`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeaders(),
          },
          body: JSON.stringify({
            question: text,
            repo: activeRepo,
            channel,
            history: messages.slice(-6), // Last 6 messages for context
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("No response body");
        }

        readerRef.current = reader;
        const decoder = new TextDecoder();
        let buffer = ""; // Buffer for incomplete lines across chunks
        let receivedMetadata = false;

        while (true) {
          const { done, value } = await reader.read();
          
          if (done) {
            // Stream closed - check if we received metadata
            if (!receivedMetadata) {
              // Mark message as error if stream closed without metadata
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        streaming: false,
                        content:
                          contentRef.current ||
                          "Response was incomplete. The service may be under load.",
                        error: true,
                      }
                    : m
                )
              );
            }
            break;
          }

          // Decode chunk and add to buffer
          buffer += decoder.decode(value, { stream: true });
          
          // Split by newlines
          const lines = buffer.split("\n");
          
          // Keep last incomplete line in buffer
          buffer = lines.pop() || "";

          // Process complete lines
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6)) as SSEEvent;

                if (data.type === "token") {
                  // Append token using ref to avoid stale closure
                  contentRef.current += data.text;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? { ...m, content: contentRef.current }
                        : m
                    )
                  );
                } else if (data.type === "metadata") {
                  // Finalize message with all metadata
                  receivedMetadata = true;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId
                        ? {
                            ...m,
                            streaming: false,
                            intent: data.intent,
                            sub_intent: data.sub_intent,
                            confidence: data.confidence,
                            citations: data.citations,
                            source_breakdown: data.source_breakdown,
                            chain_steps: data.chain_steps,
                            follow_up_suggestions: data.follow_up_suggestions,
                          }
                        : m
                    )
                  );
                }
              } catch (parseError) {
                console.error("Failed to parse SSE event:", parseError);
              }
            }
          }
        }
      } catch (error) {
        console.error("Streaming error:", error);
        // Mark message as error
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? {
                  ...m,
                  streaming: false,
                  content:
                    contentRef.current ||
                    "Response was incomplete. The service may be under load.",
                  error: true,
                }
              : m
          )
        );
      } finally {
        setIsStreaming(false);
        readerRef.current = null;
      }
    },
    [activeRepo, authHeaders, messages]
  );

  const retryMessage = useCallback(
    (messageId: string) => {
      // Find the failed message and remove it
      setMessages((prev) => prev.filter((m) => m.id !== messageId));
      
      // Resend the last user message
      if (lastUserMessageRef.current) {
        sendMessage(lastUserMessageRef.current, lastChannelRef.current);
      }
    },
    [sendMessage]
  );

  return {
    messages,
    isStreaming,
    sendMessage,
    stopStreaming,
    retryMessage,
  };
}
