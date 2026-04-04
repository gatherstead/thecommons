import { useState } from 'react';

export function useToggleSet<T>(initial: T[] = []) {
    const [selected, setSelected] = useState<T[]>(initial);

    const toggle = (item: T) => {
        setSelected(prev =>
            prev.includes(item)
                ? prev.filter(t => t !== item)
                : [...prev, item]
        );
    };

    const clear = () => setSelected([]);

    return { selected, toggle, clear, set: setSelected };
}
