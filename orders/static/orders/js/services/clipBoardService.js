export function maskSequenceCode(sequenceCode) {
    const parts = (sequenceCode || '').split('-');
    if (parts.length === 6) {
        parts[0] = '****';
        parts[1] = '***';
        parts[2] = '***';
        parts[3] = '*';
    }
    return parts.join('-');
}

