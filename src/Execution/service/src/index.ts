import express from 'express';
import { WebSocketServer } from 'ws';
import * as GainsSDK from '@gainsnetwork/sdk';
import dotenv from 'dotenv';
import { TradeRequest, Position, OrderBook, TradeUpdate } from './types';

dotenv.config();

const app = express();
const port = process.env.PORT || 3000;

// Initialize WebSocket server
const wss = new WebSocketServer({ noServer: true });

// Initialize Gains SDK
// Add your SDK initialization here

// Track connected clients
const clients = new Set<WebSocket>();

app.use(express.json());

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

// Enhanced trade execution endpoint
app.post('/execute', async (req, res) => {
  try {
    const tradeRequest: TradeRequest = req.body;
    
    // Validate trade parameters
    if (!tradeRequest.symbol || !tradeRequest.amount || !tradeRequest.leverage) {
      throw new Error('Missing required trade parameters');
    }

    // Add trade execution logic using GainsSDK
    const tradeUpdate: TradeUpdate = {
      type: 'EXECUTION',
      data: tradeRequest,
      timestamp: Date.now()
    };

    // Broadcast trade update to all connected clients
    broadcast(tradeUpdate);
    
    res.json({ status: 'success', message: 'Trade executed', data: tradeUpdate });
  } catch (error) {
    const errorUpdate: TradeUpdate = {
      type: 'ERROR',
      data: { message: error.message },
      timestamp: Date.now()
    };
    broadcast(errorUpdate);
    res.status(500).json({ status: 'error', message: error.message });
  }
});

// Enhanced position management endpoint
app.get('/positions', async (req, res) => {
  try {
    // Add position fetching logic using GainsSDK
    const positions: Position[] = [];
    res.json({ status: 'success', positions });
  } catch (error) {
    res.status(500).json({ status: 'error', message: error.message });
  }
});

// Order book endpoint
app.get('/orderbook/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    // Add order book fetching logic using GainsSDK
    const orderBook: OrderBook = {
      symbol,
      bids: [],
      asks: []
    };
    res.json({ status: 'success', orderBook });
  } catch (error) {
    res.status(500).json({ status: 'error', message: error.message });
  }
});

// Market price endpoint
app.get('/price/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    // Add price fetching logic using GainsSDK
    const price = 0; // Replace with actual price
    res.json({ status: 'success', symbol, price });
  } catch (error) {
    res.status(500).json({ status: 'error', message: error.message });
  }
});

// Broadcast function for WebSocket updates
function broadcast(message: TradeUpdate) {
  const messageStr = JSON.stringify(message);
  clients.forEach(client => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(messageStr);
    }
  });
}

const server = app.listen(port, () => {
  console.log(`Execution service running on port ${port}`);
});

// WebSocket handling
server.on('upgrade', (request, socket, head) => {
  wss.handleUpgrade(request, socket, head, (ws) => {
    wss.emit('connection', ws, request);
  });
});

wss.on('connection', (ws) => {
  console.log('Client connected');
  clients.add(ws);
  
  ws.on('message', async (message) => {
    try {
      const data = JSON.parse(message.toString());
      
      // Handle real-time trading messages
      if (data.type === 'TRADE') {
        const tradeRequest: TradeRequest = data.data;
        // Add trade execution logic here
        const tradeUpdate: TradeUpdate = {
          type: 'EXECUTION',
          data: tradeRequest,
          timestamp: Date.now()
        };
        broadcast(tradeUpdate);
      }
    } catch (error) {
      const errorUpdate: TradeUpdate = {
        type: 'ERROR',
        data: { message: error.message },
        timestamp: Date.now()
      };
      ws.send(JSON.stringify(errorUpdate));
    }
  });

  ws.on('close', () => {
    clients.delete(ws);
    console.log('Client disconnected');
  });
});
