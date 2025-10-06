import { useEffect, useRef, useState } from 'react';
import { getVideoStatus } from '../services/api';
import { useOnClickOutside } from '../utils/useOnClickOutside';
import { getStatusColor } from '../utils/utils';

export const VideoViewer = ({ id, onClose }) => {
  const [videoDetails, setVideoDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    // fetch video details by id
    if (id) {
      fetchVideo(id);
    }
  }, [id]);
  const contentBoxRef = useRef(null);
  const fetchVideo = async (id) => {
    try {
      setLoading(true);
      const response = await getVideoStatus(id);
      setVideoDetails(response);
    } catch (err) {
      console.error('Error fetching video details:', err);
    } finally {
      setLoading(false);
    }
  };
  useOnClickOutside(contentBoxRef, () => {
    setVideoDetails(null);
    onClose();
  });
  console.log('Video details:', videoDetails);
  return (
    <div className='video-viewer-overlay'>
      <div className='video-viewer-content' ref={contentBoxRef}>
        <h2>Video Preview</h2>
        {loading && <p>Loading...</p>}
        {!loading && !videoDetails && <p>No video details available.</p>}
        {!loading && videoDetails?.videoUrl && (
          <>
            <div className='video-viewer-tags'>
              <span>
                ID: <strong>{videoDetails.id}</strong>
              </span>
              <span>
                Status: <strong style={{ color: getStatusColor(videoDetails.status) }}>{videoDetails.status}</strong>
              </span>
              <span>
                Created At: <strong>{new Date(videoDetails.createdAt).toLocaleString()}</strong>
              </span>
            </div>
            <div className='video-viewer-vid-container'>
              <video
                key={videoDetails.videoUrl} // key to force reload when URL changes
                src={videoDetails.videoUrl}
                controls
                autoPlay
              />
              <p>{videoDetails?.prompt}</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
