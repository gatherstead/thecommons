'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { SignInForm } from './signin/SignInForm';
import { JoinForm } from './join/JoinForm';

type Tab = 'signin' | 'join';

const TABS: { id: Tab; label: string; path: string }[] = [
    { id: 'signin', label: 'Sign In', path: '/signin' },
    { id: 'join', label: 'Create Account', path: '/join' },
];

function tabForPath(pathname: string): Tab {
    return pathname.startsWith('/join') ? 'join' : 'signin';
}

export function AuthPanel({ initialTab }: { initialTab: Tab }) {
    const searchParams = useSearchParams();
    const redirectTo = searchParams.get('redirect_to');
    const query = redirectTo ? `?redirect_to=${encodeURIComponent(redirectTo)}` : '';

    const [tab, setTab] = useState<Tab>(initialTab);

    // Shared so switching tabs doesn't make someone retype what they just typed.
    const [email, setEmail] = useState('');

    // Autofocus the first field on arrival, but not on a tab switch — that would
    // yank focus off the tab the user just activated.
    const [hasSwitched, setHasSwitched] = useState(false);

    const navRef = useRef<HTMLElement>(null);
    const tabRefs = useRef<Partial<Record<Tab, HTMLAnchorElement | null>>>({});
    const [marker, setMarker] = useState({ left: 0, width: 0 });
    const [markerReady, setMarkerReady] = useState(false);

    useLayoutEffect(() => {
        function measure() {
            const el = tabRefs.current[tab];
            if (!el) return;
            setMarker({ left: el.offsetLeft, width: el.offsetWidth });
        }
        measure();
        // The marker is measured, so it has to re-measure when the labels reflow.
        window.addEventListener('resize', measure);
        return () => window.removeEventListener('resize', measure);
    }, [tab]);

    useEffect(() => {
        // Deferred so the first paint places the marker instead of sliding it
        // in from the left edge.
        const id = requestAnimationFrame(() => setMarkerReady(true));
        return () => cancelAnimationFrame(id);
    }, []);

    const bodyRef = useRef<HTMLDivElement>(null);
    const [bodyHeight, setBodyHeight] = useState<number>();

    useLayoutEffect(() => {
        const el = bodyRef.current;
        if (!el) return;
        const observer = new ResizeObserver(() => setBodyHeight(el.offsetHeight));
        observer.observe(el);
        setBodyHeight(el.offsetHeight);
        return () => observer.disconnect();
    }, []);

    const select = useCallback(
        (next: Tab, path: string) => {
            setTab(next);
            setHasSwitched(true);
            // Shallow update: the URL stays honest without a route change, which
            // is what used to remount the shell and flash the artwork.
            window.history.pushState(null, '', `${path}${query}`);
        },
        [query],
    );

    useEffect(() => {
        function syncFromUrl() {
            setTab(tabForPath(window.location.pathname));
        }
        window.addEventListener('popstate', syncFromUrl);
        return () => window.removeEventListener('popstate', syncFromUrl);
    }, []);

    return (
        <>
            <nav ref={navRef} aria-label="Account access" className="portal-tabs">
                {TABS.map(({ id, label, path }) => (
                    <Link
                        key={id}
                        ref={el => {
                            tabRefs.current[id] = el;
                        }}
                        href={`${path}${query}`}
                        aria-current={tab === id ? 'page' : undefined}
                        onClick={e => {
                            // Let modified clicks open a real new tab.
                            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                            e.preventDefault();
                            select(id, path);
                        }}
                        className={`portal-tab ${tab === id ? 'is-active' : ''}`}
                    >
                        {label}
                    </Link>
                ))}
                <span
                    aria-hidden
                    className={`portal-tab-marker ${markerReady ? 'is-ready' : ''}`}
                    style={{ transform: `translateX(${marker.left}px)`, width: marker.width }}
                />
            </nav>

            <div className="portal-body mt-8" style={{ height: bodyHeight }}>
                <div ref={bodyRef}>
                    <div key={tab} className="portal-form">
                        {tab === 'signin' ? (
                            <SignInForm
                                email={email}
                                onEmailChange={setEmail}
                                autoFocus={!hasSwitched}
                            />
                        ) : (
                            <JoinForm
                                email={email}
                                onEmailChange={setEmail}
                                autoFocus={!hasSwitched}
                            />
                        )}
                    </div>
                </div>
            </div>
        </>
    );
}
