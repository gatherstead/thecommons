'use client';

import { useMessageStack } from '../../hooks/useMessageStack';
import { Banner } from '../ui/Banner';

export function MessageStackBanner() {
    const { current, dismiss } = useMessageStack();

    if (!current) return null;

    return (
        <Banner
            variant={current.variant}
            sticky
            onDismiss={() => dismiss(current.id)}
        >
            {current.content}
        </Banner>
    );
}
