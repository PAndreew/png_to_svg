FROM node:20-slim

WORKDIR /planner

COPY package.json tsconfig.json ./
RUN npm install

COPY src ./src

EXPOSE 8787

CMD ["npm", "run", "start"]
