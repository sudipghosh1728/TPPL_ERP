import { MongoClient } from 'mongodb';
import { loadEnvFile } from 'node:process';
import { fileURLToPath } from 'node:url';

// Server-side only. Never bundle this module or credentials into the browser.
try {
  loadEnvFile(fileURLToPath(new URL('./.env', import.meta.url)));
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}

let client;
let connecting;

export async function connectToMongoDB() {
  if (!process.env.MONGODB_URI) throw new Error('Set MONGODB_URI in .env or the environment.');
  if (!connecting) {
    client = new MongoClient(process.env.MONGODB_URI, {
      serverSelectionTimeoutMS: 8000,
      connectTimeoutMS: 8000,
    });
    connecting = (async () => {
      try {
        await client.connect();
        await client.db('admin').command({ ping: 1 });
        return client;
      } catch {
        await client.close().catch(() => {});
        client = undefined;
        connecting = undefined;
        throw new Error('MongoDB connection failed. Check Atlas network access, cluster status, and private credentials.');
      }
    })();
  }
  return connecting;
}

// Call only when the application terminates, after active requests finish.
export async function disconnectFromMongoDB() {
  if (connecting) await connecting.catch(() => {});
  if (client) await client.close();
  client = undefined;
  connecting = undefined;
}
