#!/bin/bash

show_menu() {
    echo ""
    echo "=========================================================="
    echo "Masterproef - Research Tool"
    echo "=========================================================="
    echo ""
    echo "1. Start the application"
    echo "2. Stop the application"
    echo "3. Run post-hoc classification script"
    echo "4. Clean / Reset (removes Docker containers, networks, and images)"
    echo "5. Exit"
    echo ""
    read -p "Choose an option (1/2/3/4/5): " choice
}

start_app() {
    if [ ! -f .env ]; then
        echo ""
        echo "=========================================================="
        echo "First-time Setup: Configuring .env file"
        echo "=========================================================="
        echo "If you want to enable AI features, please enter your details."
        echo "(Or press Enter to skip and leave them blank)"
        echo ""
        read -p "Enter AZURE_OPENAI_API_KEY: " api_key
        read -p "Enter AZURE_OPENAI_ENDPOINT: " endpoint
        read -p "Enter GROQ_API_KEY: " groq_key
        echo ""

        cp .env.example .env 2>/dev/null

        # Replace the placeholders in .env
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|AZURE_OPENAI_API_KEY=|AZURE_OPENAI_API_KEY=\"$api_key\"|g" .env
            sed -i '' "s|AZURE_OPENAI_ENDPOINT=|AZURE_OPENAI_ENDPOINT=\"$endpoint\"|g" .env
            sed -i '' "s|GROQ_API_KEY=|GROQ_API_KEY=\"$groq_key\"|g" .env
        else
            sed -i "s|AZURE_OPENAI_API_KEY=|AZURE_OPENAI_API_KEY=\"$api_key\"|g" .env
            sed -i "s|AZURE_OPENAI_ENDPOINT=|AZURE_OPENAI_ENDPOINT=\"$endpoint\"|g" .env
            sed -i "s|GROQ_API_KEY=|GROQ_API_KEY=\"$groq_key\"|g" .env
        fi
        
        echo ".env file configured successfully."
        echo ""
    fi

    echo ""
    echo "Building and starting Docker containers (this may take a moment)..."
    echo ""
    docker compose build --quiet
    docker compose up -d
    echo ""
    echo "SUCCESS! Opening your browser to http://localhost"
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
    echo "Stopping the application..."
    echo ""
    docker compose down
    echo ""
    echo "Successfully stopped!"
}

run_posthoc() {
    echo ""
    echo "Starting post-hoc classification in Docker..."
    echo ""
    docker compose build --quiet backend
    docker compose run --rm -v ./backend:/app backend python post_hoc_classification.py
}

clean_app() {
    echo ""
    echo "=========================================================="
    echo "Warning: This will delete Docker containers, images, and networks."
    echo "Your .env file and collected data in the results folder will NOT be touched."
    echo "=========================================================="
    echo ""
    read -p "Are you sure you want to clean? (y/n): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        return
    fi
    echo ""
    echo "Cleaning up application resources..."
    echo ""
    docker compose down --rmi all --volumes --remove-orphans
    echo ""
    echo "Successfully cleaned!"
}

while true; do
    show_menu
    case $choice in
        1) start_app ;;
        2) stop_app ;;
        3) run_posthoc ;;
        4) clean_app ;;
        5) exit 0 ;;
        *) echo "Invalid choice. Please try again." ;;
    esac
done
