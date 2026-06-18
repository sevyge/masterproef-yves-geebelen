function backendUrl() {
    const hostname = window.location.hostname;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
        return "http://localhost:8000";
    }
    return "https://backend-masterproef.onrender.com";
}