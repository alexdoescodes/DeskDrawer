.pragma library

function remainingLabel(deadlineSeconds, nowSeconds) {
    const left = deadlineSeconds - nowSeconds;
    if (left <= 0) {
        return "expired";
    }
    if (left < 60) {
        return "<1m";
    }
    const minutes = Math.floor(left / 60);
    if (minutes < 60) {
        return minutes + "m";
    }
    return Math.floor(minutes / 60) + "h";
}

function isUrgent(deadlineSeconds, nowSeconds) {
    return (deadlineSeconds - nowSeconds) < 3600;
}
