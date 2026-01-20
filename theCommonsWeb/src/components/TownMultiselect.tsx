import { useState, useRef, useEffect } from 'react';

export const TOWNS = [
    { id: 'carrboro', name: 'Carrboro' },
    { id: 'chapel-hill', name: 'Chapel Hill' },
    { id: 'pittsboro', name: 'Pittsboro' },
    { id: 'hillsborough', name: 'Hillsborough' },
    { id: 'durham', name: 'Durham' },
    { id: 'raleigh', name: 'Raleigh' },
    { id: 'cary', name: 'Cary' },
    { id: 'apex', name: 'Apex' },
] as const;

export type TownId = typeof TOWNS[number]['id'];

interface TownMultiselectProps {
    selectedTowns: TownId[];
    onTownToggle: (townId: TownId) => void;
}

export function TownMultiselect({ selectedTowns, onTownToggle }: TownMultiselectProps) {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const selectedNames = selectedTowns.length > 0
        ? TOWNS.filter(t => selectedTowns.includes(t.id)).map(t => t.name).join(', ')
        : 'All Towns';

    return (
        <div ref={dropdownRef} className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full px-4 py-3 border-2 border-[var(--color-border)] bg-[var(--color-paper)] text-left flex justify-between items-center cursor-pointer hover:bg-[#ebe7de] transition-colors"
            >
                <span className="font-[var(--font-headline)] text-lg truncate pr-2">
                    {selectedNames}
                </span>
                <svg
                    className={`w-5 h-5 transition-transform flex-shrink-0 ${isOpen ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {isOpen && (
                <div className="absolute z-50 w-full mt-1 border-2 border-[var(--color-border)] bg-[var(--color-paper)] shadow-lg max-h-64 overflow-y-auto">
                    {TOWNS.map((town) => {
                        const isSelected = selectedTowns.includes(town.id);
                        return (
                            <button
                                key={town.id}
                                onClick={() => onTownToggle(town.id)}
                                className={`w-full px-4 py-2 text-left flex items-center gap-3 cursor-pointer transition-colors ${isSelected ? 'bg-[var(--color-ink)] text-[var(--color-paper)]' : 'hover:bg-[#ebe7de]'
                                    }`}
                            >
                                <span className={`w-4 h-4 border-2 flex items-center justify-center flex-shrink-0 ${isSelected ? 'border-[var(--color-paper)] bg-[var(--color-paper)]' : 'border-[var(--color-border)]'
                                    }`}>
                                    {isSelected && (
                                        <svg className="w-3 h-3 text-[var(--color-ink)]" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                        </svg>
                                    )}
                                </span>
                                <span className="font-[var(--font-body)]">{town.name}</span>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
