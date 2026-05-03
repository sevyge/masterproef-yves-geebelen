FROM nginx:alpine

# Copy frontend static files to Nginx's default directory
COPY . /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
