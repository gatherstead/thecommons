import { Suspense } from 'react';
import { PortalShell } from '../PortalShell';
import { AuthPanel } from '../AuthPanel';

export default function JoinPage() {
    return (
        <PortalShell>
            <Suspense fallback={null}>
                <AuthPanel initialTab="join" />
            </Suspense>
        </PortalShell>
    );
}
