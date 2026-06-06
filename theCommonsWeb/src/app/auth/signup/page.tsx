import { Suspense } from 'react';
import { AuthFlow } from '../AuthFlow';

export default function SignupPage() {
    return (
        <Suspense fallback={null}>
            <AuthFlow defaultSignIn={false} />
        </Suspense>
    );
}
