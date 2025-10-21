import { useState, useEffect } from 'react';
import { getVideos, refreshVideoUrl, deleteVideo } from '../services/api';
import { getModelLabel, getStatusColor } from '../utils/utils';
import { VideoViewer } from './VideoViewer';
import { useMyContext } from '../context/context-provider';

export default function VideoList({ refreshTrigger }) {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showVideoId, setShowVideoId] = useState(null);
  const [refreshingUrls, setRefreshingUrls] = useState(new Set());
  const [deletingVideos, setDeletingVideos] = useState(new Set());

  const context = useMyContext();

  useEffect(() => {
    fetchVideos();
  }, [refreshTrigger]);

  const fetchVideos = async () => {
    setLoading(true);
    setError('');

    try {
      const data = await getVideos();
      setVideos(data.videos || []);
    } catch (err) {
      setError(err.message || 'Failed to load videos');
      console.error('Error fetching videos:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshUrl = async (videoId) => {
    setRefreshingUrls((prev) => new Set(prev).add(videoId));

    try {
      const result = await refreshVideoUrl(videoId);

      // Update the video in the list with new URL
      setVideos((prevVideos) => prevVideos.map((video) => (video.id === videoId ? { ...video, videoUrl: result.videoUrl } : video)));
    } catch (err) {
      console.error('Error refreshing URL:', err);
      alert(err.message || 'Failed to refresh URL');
    } finally {
      setRefreshingUrls((prev) => {
        const newSet = new Set(prev);
        newSet.delete(videoId);
        return newSet;
      });
    }
  };

  const handleDownload = async (videoUrl, videoId) => {
    try {
      const response = await fetch(videoUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `video-${videoId}.mp4`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Download failed:', err);
      // Fallback to opening in new tab
      window.open(videoUrl, '_blank');
    }
  };

  const handleDelete = async (videoId) => {
    if (!confirm('Are you sure you want to delete this video? This action cannot be undone.')) {
      return;
    }

    setDeletingVideos((prev) => new Set(prev).add(videoId));

    try {
      await deleteVideo(videoId);
      // Remove video from list
      setVideos((prevVideos) => prevVideos.filter((video) => video.id !== videoId));
    } catch (err) {
      console.error('Error deleting video:', err);
      alert(err.message || 'Failed to delete video');
    } finally {
      setDeletingVideos((prev) => {
        const newSet = new Set(prev);
        newSet.delete(videoId);
        return newSet;
      });
    }
  };

  if (loading) {
    return <div className='video-list loading'>Loading videos...</div>;
  }

  if (error) {
    return (
      <div className='video-list error'>
        <p>{error}</p>
        <button onClick={fetchVideos}>Retry</button>
      </div>
    );
  }

  return (
    <div className='video-list'>
      <div className='list-header'>
        <h2>Generated Videos</h2>
        <button onClick={fetchVideos} className='refresh-btn'>
          Refresh
        </button>
      </div>

      {videos.length === 0 ? (
        <p className='no-videos'>No videos generated yet</p>
      ) : (
        <div className='videos-grid'>
          {videos.map((video) => (
            <div key={video.id} className='video-card'>
              <div className='video-info'>
                <h3>{video.prompt}</h3>
                <p className='video-date'>{new Date(video.createdAt).toLocaleString()}</p>
                <div className='video-status'>
                  <span>
                    <span className='status-indicator' style={{ backgroundColor: getStatusColor(video.status) }} />
                    <span>{video.status}</span>
                  </span>
                  {video.model && (
                    <div>
                      Model: <span className={`video-model ${getModelLabel(video.model).className}`}>{getModelLabel(video.model).name}</span>
                    </div>
                  )}
                </div>
              </div>

              {video.status === 'completed' && (
                <div className='video-actions'>
                  {video.videoUrl && (
                    <>
                      <button className='view-btn' onClick={() => setShowVideoId(video.id)}>
                        View Video
                      </button>
                      <button onClick={() => handleDownload(video.videoUrl, video.id)} className='download-btn'>
                        Download
                      </button>
                      <button onClick={() => handleRefreshUrl(video.id)} disabled={refreshingUrls.has(video.id)} className='refresh-url-btn'>
                        {refreshingUrls.has(video.id) ? 'ReGening...' : 'ReGen URL'}
                      </button>
                      <button onClick={() => context.updateValue('prompt', video.prompt)} className='edit-prompt-btn'>
                        Reuse Prompt
                      </button>
                      <button onClick={() => handleDelete(video.id)} disabled={deletingVideos.has(video.id)} className='delete-btn'>
                        {deletingVideos.has(video.id) ? 'Deleting...' : 'Delete'}
                      </button>
                    </>
                  )}
                </div>
              )}
              {video.status === 'failed' && (
                <div className='video-actions'>
                  <p className='error-text'>Video generation failed with error: {video.error}.</p>
                  <button onClick={() => handleDelete(video.id)} disabled={deletingVideos.has(video.id)} className='delete-btn'>
                    {deletingVideos.has(video.id) ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              )}

              {video.status === 'processing' && (
                <div className='processing-indicator'>
                  <div className='spinner'></div>
                  <span>Processing...</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {showVideoId && (
        <div className='video-modal'>
          <VideoViewer id={showVideoId} onClose={() => setShowVideoId(null)} />
        </div>
      )}
    </div>
  );
}
