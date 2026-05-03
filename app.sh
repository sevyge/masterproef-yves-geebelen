#!/bin/bash

show_menu() {
    echo ""
    echo "=========================================================="
    echo "   Masterproef - Research Tool"
    echo "=========================================================="
    echo ""
    echo "   1. Start the application"
    echo "   2. Stop the application"
    echo "   3. Exit"
    echo ""
    read -p "   Choose an option (1/2/3): " choice
}

start_app() {
    if [ ! -f .env ]; then
        echo ""
        echo "   Warning: .env file not found!"
        echo "   Creating .env from .env.example with default values."
        echo "   AI features will be disabled."
        echo ""
        echo "   To enable AI, edit .env and add your Azure OpenAI credentials."
        echo ""
        cp .env.example .env 2>/dev/null
    fi

    echo ""
    echo "   Starting the application..."
    echo ""
    docker compose up -d --build
    echo ""
    echo "   SUCCESS! Opening your browser to http://localhost"
    echo ""
    sleep 3
    if command -v xdg-open > /dev/null; then
        xdg-open http://localhost
    elif command -v open > /dev/null; then
        open http://localhost
    fi
}

stop_app() {
    echo ""
    echo "   Stopping the application..."
    echo ""
    docker compose down
    echo ""
    echo "   Successfully stopped!"
}

while true; do
    show_menu
    case $choice in
        1) start_app ;;
        2) stop_app ;;
        3) exit 0 ;;
        *) echo "   Invalid choice. Please try again." ;;
    esac
done
