export function riskLabel(risk: string): string;
export function actionLabel(action: string, retryAllowed: boolean): string;
export function isRetryDisabled(advice: { allowed?: { retry?: boolean } } | null | undefined): boolean;
export function recoveryCardVisible(status: string): boolean;
