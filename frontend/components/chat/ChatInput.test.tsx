import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "./ChatInput";

describe("ChatInput", () => {
  const mockOnSend = vi.fn();
  const mockOnStop = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Basic rendering", () => {
    it("renders textarea and send button", () => {
      render(<ChatInput onSend={mockOnSend} />);
      
      expect(screen.getByPlaceholderText(/Ask anything about your system/i)).toBeInTheDocument();
      expect(screen.getByLabelText("Send message")).toBeInTheDocument();
    });

    it("renders channel mode pill with default 'Web'", () => {
      render(<ChatInput onSend={mockOnSend} />);
      
      expect(screen.getByText("Web")).toBeInTheDocument();
    });

    it("shows disabled placeholder when disabled", () => {
      render(<ChatInput onSend={mockOnSend} disabled />);
      
      expect(screen.getByPlaceholderText(/Select a repository to start asking/i)).toBeInTheDocument();
    });
  });

  describe("Channel mode cycling", () => {
    it("cycles from Web to CLI Preview on click", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const channelButton = screen.getByText("Web");
      await user.click(channelButton);
      
      expect(screen.getByText("CLI Preview")).toBeInTheDocument();
    });

    it("cycles from CLI Preview back to Web", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const channelButton = screen.getByText("Web");
      await user.click(channelButton); // Web -> CLI Preview
      await user.click(screen.getByText("CLI Preview")); // CLI Preview -> Web
      
      expect(screen.getByText("Web")).toBeInTheDocument();
    });

    it("sends channel mode with message", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      const channelButton = screen.getByText("Web");
      
      // Switch to CLI Preview
      await user.click(channelButton);
      
      // Type and send message
      await user.type(textarea, "test message");
      await user.keyboard("{Enter}");
      
      expect(mockOnSend).toHaveBeenCalledWith("test message", "cli");
    });
  });

  describe("Message sending", () => {
    it("sends message on Enter key", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      await user.type(textarea, "test message{Enter}");
      
      expect(mockOnSend).toHaveBeenCalledWith("test message", "web");
    });

    it("adds new line on Shift+Enter", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i) as HTMLTextAreaElement;
      await user.type(textarea, "line 1{Shift>}{Enter}{/Shift}line 2");
      
      expect(textarea.value).toContain("\n");
      expect(mockOnSend).not.toHaveBeenCalled();
    });

    it("sends message on send button click", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      const sendButton = screen.getByLabelText("Send message");
      
      await user.type(textarea, "test message");
      await user.click(sendButton);
      
      expect(mockOnSend).toHaveBeenCalledWith("test message", "web");
    });

    it("clears textarea after sending", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i) as HTMLTextAreaElement;
      await user.type(textarea, "test message{Enter}");
      
      expect(textarea.value).toBe("");
    });

    it("trims whitespace from message", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      await user.type(textarea, "  test message  {Enter}");
      
      expect(mockOnSend).toHaveBeenCalledWith("test message", "web");
    });

    it("does not send empty message", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      await user.type(textarea, "   {Enter}");
      
      expect(mockOnSend).not.toHaveBeenCalled();
    });
  });

  describe("Conditional button rendering", () => {
    it("shows send button when not streaming", () => {
      render(<ChatInput onSend={mockOnSend} isStreaming={false} />);
      
      expect(screen.getByLabelText("Send message")).toBeInTheDocument();
      expect(screen.queryByLabelText("Stop streaming")).not.toBeInTheDocument();
    });

    it("shows stop button when streaming", () => {
      render(<ChatInput onSend={mockOnSend} onStop={mockOnStop} isStreaming={true} />);
      
      expect(screen.getByLabelText("Stop streaming")).toBeInTheDocument();
      expect(screen.queryByLabelText("Send message")).not.toBeInTheDocument();
    });

    it("calls onStop when stop button clicked", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} onStop={mockOnStop} isStreaming={true} />);
      
      const stopButton = screen.getByLabelText("Stop streaming");
      await user.click(stopButton);
      
      expect(mockOnStop).toHaveBeenCalled();
    });

    it("disables send button when textarea is empty", () => {
      render(<ChatInput onSend={mockOnSend} />);
      
      const sendButton = screen.getByLabelText("Send message");
      expect(sendButton).toBeDisabled();
    });

    it("enables send button when textarea has content", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      const sendButton = screen.getByLabelText("Send message");
      
      await user.type(textarea, "test");
      
      expect(sendButton).not.toBeDisabled();
    });

    it("disables send button when disabled prop is true", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} disabled />);
      
      const textarea = screen.getByPlaceholderText(/Select a repository/i);
      const sendButton = screen.getByLabelText("Send message");
      
      await user.type(textarea, "test");
      
      expect(sendButton).toBeDisabled();
    });
  });

  describe("Keyboard shortcut", () => {
    it("focuses textarea on Cmd+/ (Mac)", () => {
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      
      fireEvent.keyDown(document, { key: "/", metaKey: true });
      
      expect(textarea).toHaveFocus();
    });

    it("focuses textarea on Ctrl+/ (Windows)", () => {
      render(<ChatInput onSend={mockOnSend} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      
      fireEvent.keyDown(document, { key: "/", ctrlKey: true });
      
      expect(textarea).toHaveFocus();
    });
  });

  describe("Disabled state", () => {
    it("prevents sending when disabled", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} disabled />);
      
      const textarea = screen.getByPlaceholderText(/Select a repository/i);
      await user.type(textarea, "test{Enter}");
      
      expect(mockOnSend).not.toHaveBeenCalled();
    });

    it("prevents sending when streaming", async () => {
      const user = userEvent.setup();
      render(<ChatInput onSend={mockOnSend} isStreaming={true} />);
      
      const textarea = screen.getByPlaceholderText(/Ask anything about your system/i);
      await user.type(textarea, "test{Enter}");
      
      expect(mockOnSend).not.toHaveBeenCalled();
    });
  });
});
