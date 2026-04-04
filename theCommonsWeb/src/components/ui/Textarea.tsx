import { useId, type TextareaHTMLAttributes } from 'react';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
    label: string;
    error?: string;
}

export function Textarea({ label, error, id: providedId, ...props }: TextareaProps) {
    const generatedId = useId();
    const id = providedId || generatedId;
    const errorId = `${id}-error`;

    return (
        <div>
            <label htmlFor={id} className="block text-xs uppercase tracking-wider font-bold mb-1">
                {label}
            </label>
            <textarea
                id={id}
                aria-describedby={error ? errorId : undefined}
                className="w-full border border-[var(--color-border)] p-2 font-[var(--font-body)] text-sm focus:border-[var(--color-accent)] outline-none resize-none bg-transparent"
                {...props}
            />
            {error && (
                <p id={errorId} className="text-[var(--color-accent)] text-xs mt-1" role="alert">
                    {error}
                </p>
            )}
        </div>
    );
}
