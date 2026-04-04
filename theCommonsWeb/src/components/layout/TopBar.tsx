import type { TownOption } from '../../models/eventsModels';

interface TopBarProps {
    towns: TownOption[];
    selectedTowns: string[];
    onTownToggle: (townId: string) => void;
    onClearFilters: () => void;
}

// TODO: Replace this hardcoded list with towns from the database.
// These are NC towns planned for future coverage — they should be added
// to the towns table and fetched via the API alongside active towns.
const PLACEHOLDER_TOWN_NAMES = [
    'Raleigh',
    'Cary',
    'Apex',
    'Morrisville',
    'Wake Forest',
    'Fuquay-Varina',
    'Holly Springs',
    'Garner',
    'Clayton',
    'Hillsborough',
    'Mebane',
    'Burlington',
    'Chatham County',
    'Alamance County',
];

export function TopBar({ towns, selectedTowns, onTownToggle, onClearFilters }: TopBarProps) {
    const hasSelection = selectedTowns.length > 0;

    // Filter out placeholder towns that already exist in the active DB list
    const activeTownNames = new Set(towns.map(t => t.name.toLowerCase()));
    const placeholderTowns = PLACEHOLDER_TOWN_NAMES.filter(
        name => !activeTownNames.has(name.toLowerCase())
    );

    return (
        <nav
            aria-label="Filter by town"
            className="border-b border-[var(--color-border-light)] bg-[var(--color-bg)]"
        >
            <div className="max-w-[1200px] mx-auto px-4 py-1.5 flex items-center overflow-x-auto whitespace-nowrap scrollbar-hide">
                <span className="text-[10px] font-black uppercase tracking-widest text-[var(--color-accent)] mr-3 shrink-0">
                    Towns:
                </span>

                {/* All — deselects town filter */}
                <button
                    onClick={onClearFilters}
                    aria-pressed={!hasSelection}
                    className={`text-xs uppercase tracking-wider shrink-0 cursor-pointer bg-transparent border-none transition-colors ${
                        !hasSelection
                            ? 'font-black text-[var(--color-accent)] underline'
                            : 'hover:text-[var(--color-accent)]'
                    }`}
                >
                    All
                </button>

                {/* Active towns — from database */}
                {towns.map((town) => {
                    const isSelected = selectedTowns.includes(town.slug);
                    return (
                        <span key={town.slug} className="flex items-center shrink-0">
                            <span className="mx-2 text-[var(--color-border-light)] text-xs select-none" aria-hidden="true">|</span>
                            <button
                                onClick={() => onTownToggle(town.slug)}
                                aria-pressed={isSelected}
                                className={`text-xs uppercase tracking-wider cursor-pointer bg-transparent border-none transition-colors ${
                                    isSelected
                                        ? 'font-black text-[var(--color-accent)] underline'
                                        : 'hover:text-[var(--color-accent)]'
                                }`}
                            >
                                {town.name}
                            </button>
                        </span>
                    );
                })}

                {/* Placeholder towns — coming soon, not yet in database */}
                {placeholderTowns.map((name) => (
                    <span key={name} className="flex items-center shrink-0">
                        <span className="mx-2 text-[var(--color-border-light)] text-xs select-none" aria-hidden="true">|</span>
                        <span
                            className="text-xs uppercase tracking-wider text-[var(--color-border-light)] cursor-default"
                            aria-label={`${name} — coming soon`}
                            title="Coming soon"
                        >
                            {name}
                        </span>
                    </span>
                ))}
            </div>
        </nav>
    );
}
