import { Suspense } from 'react';
import { PortalShell } from '../PortalShell';
import { AuthPanel } from '../AuthPanel';

export default function SignInPage() {
    return (
        <PortalShell>
            <Suspense fallback={null}>
                <AuthPanel initialTab="signin" />
            </Suspense>
        </PortalShell>
    );
}
