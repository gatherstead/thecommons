import { Suspense } from 'react';
import { PortalShell } from '../PortalShell';
import { ForgotPasswordForm } from './ForgotPasswordForm';

export default function ForgotPasswordPage() {
    return (
        <PortalShell heading="Forgot Password?">
            <Suspense fallback={null}>
                <ForgotPasswordForm />
            </Suspense>
        </PortalShell>
    );
}
