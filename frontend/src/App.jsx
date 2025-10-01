import { useState } from 'react';
import VideoUploadForm from './components/VideoUploadForm';
import VideoList from './components/VideoList';
import { generateVideo } from './services/api';
import './App.css';

function App() {
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [notification, setNotification] = useState(null);

  const handleVideoSubmit = async ({ prompt, image }) => {
    try {
      const result = await generateVideo({ prompt, image });

      setNotification({
        type: 'success',
        message: 'Video generation started! Check the list below for updates.'
      });

      // Refresh the video list
      setRefreshTrigger(prev => prev + 1);

      // Clear notification after 5 seconds
      setTimeout(() => setNotification(null), 5000);

      return result;
    } catch (error) {
      setNotification({
        type: 'error',
        message: error.message || 'Failed to start video generation'
      });

      // Clear notification after 5 seconds
      setTimeout(() => setNotification(null), 5000);

      throw error;
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Streameye PoC Video Generator</h1>
        <p>Generate videos from images and prompts using Google's Veo 3 video creator</p>
      </header>

      {notification && (
        <div className={`notification ${notification.type}`}>
          {notification.message}
        </div>
      )}

      <main className="app-main">
        <VideoUploadForm onSubmit={handleVideoSubmit} />
        <VideoList refreshTrigger={refreshTrigger} />
      </main>

      <footer className="app-footer">
        <p>AWS Lambda + Google Veo 3</p>
      </footer>
    </div>
  );
}

export default App;
