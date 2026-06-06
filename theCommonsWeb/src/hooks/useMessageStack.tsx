'use client';

import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

export interface StackMessage {
    id: string;
    content: React.ReactNode;
    variant?: 'default' | 'accent';
}

interface MessageStackContextValue {
    push: (msg: StackMessage) => void;
    dismiss: (id: string) => void;
    current: StackMessage | null;
}

const MessageStackContext = createContext<MessageStackContextValue | null>(null);

export function MessageStackProvider({ children }: { children: React.ReactNode }) {
    const [messages, setMessages] = useState<StackMessage[]>([]);
    const [isCooldown, setIsCooldown] = useState(false);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const push = useCallback((msg: StackMessage) => {
        setMessages((prev) => {
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, msg];
        });
    }, []);

    const dismiss = useCallback((id: string) => {
        if (timerRef.current) {
            clearTimeout(timerRef.current);
            timerRef.current = null;
        }

        setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === id);
            if (idx === -1) return prev;
            const next = prev.filter((m) => m.id !== id);
            if (idx === 0 && next.length > 0) {
                setIsCooldown(true);
                timerRef.current = setTimeout(() => setIsCooldown(false), 5000);
            }
            return next;
        });
    }, []);

    const current = useMemo<StackMessage | null>(() => {
        if (isCooldown || messages.length === 0) return null;
        return messages[0];
    }, [isCooldown, messages]);

    const value = useMemo(() => ({ push, dismiss, current }), [push, dismiss, current]);

    return (
        <MessageStackContext.Provider value={value}>
            {children}
        </MessageStackContext.Provider>
    );
}

export function useMessageStack() {
    const ctx = useContext(MessageStackContext);
    if (!ctx) throw new Error('useMessageStack must be used within MessageStackProvider');
    return ctx;
}
