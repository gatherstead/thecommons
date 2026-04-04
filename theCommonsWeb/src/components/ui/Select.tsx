import { useId, type SelectHTMLAttributes } from 'react';

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
    label: string;
    error?: string;
}

export function Select({ label, error, id: providedId, children, ...props }: SelectProps) {
    const generatedId = useId();
    const id = providedId || generatedId;
    const errorId = `${id}-error`;

    return (
        <div>
            <label htmlFor={id} className="block text-xs uppercase tracking-wider font-bold mb-1">
                {label}
            </label>
            <select
                id={id}
                aria-describedby={error ? errorId : undefined}
                className="w-full border border-[var(--color-border)] p-2 font-[var(--font-body)] text-sm focus:border-[var(--color-accent)] outline-none bg-transparent"
                {...props}
            >
                {children}
            </select>
            {error && (
                <p id={errorId} className="text-[var(--color-accent)] text-xs mt-1" role="alert">
                    {error}
                </p>
            )}
        </div>
    );
}
