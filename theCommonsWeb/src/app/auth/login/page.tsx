import { Suspense } from 'react';
import { AuthFlow } from '../AuthFlow';

export default function LoginPage() {
    return (
        <Suspense fallback={null}>
            <AuthFlow defaultSignIn={true} />
        </Suspense>
    );
}
