import { RouterProvider } from 'react-router';
import { router } from './routes';
import { ThemeProvider } from '../context/ThemeContext';
import { AuthProvider } from '../context/AuthContext';
import { WebSocketProvider } from '../context/WebSocketContext';
import { Toaster } from 'sonner';

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <WebSocketProvider>
          <RouterProvider router={router} />
          <Toaster richColors position="top-right" />
        </WebSocketProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}