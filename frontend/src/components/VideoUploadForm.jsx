import { useState } from 'react';

export default function VideoUploadForm({ onSubmit }) {
  const [prompt, setPrompt] = useState('');
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      setError('Please upload a JPG or PNG file');
      return;
    }

    // Validate dimensions
    const img = new Image();
    img.onload = () => {
      if (img.width !== 1280 || img.height !== 720) {
        setError('Image must be exactly 1280x720 pixels');
        setImage(null);
        setPreview(null);
      } else {
        setError('');
        setImage(file);
        setPreview(URL.createObjectURL(file));
      }
    };
    img.src = URL.createObjectURL(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!prompt || !image) {
      setError('Please provide both a prompt and an image');
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      await onSubmit({ prompt, image });
      // Reset form after successful submission
      setPrompt('');
      setImage(null);
      setPreview(null);
    } catch (err) {
      setError(err.message || 'Failed to submit request');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="upload-form">
      <h2>Generate Video with Gemini Veo 3</h2>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="prompt">Prompt:</label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe the video you want to generate..."
            rows="4"
            disabled={isSubmitting}
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="image">Image (1280x720, JPG/PNG):</label>
          <input
            id="image"
            type="file"
            accept="image/jpeg,image/png"
            onChange={handleImageChange}
            disabled={isSubmitting}
            required
          />
        </div>

        {preview && (
          <div className="image-preview">
            <img src={preview} alt="Preview" />
            <p>Dimensions: 1280x720</p>
          </div>
        )}

        {error && <div className="error-message">{error}</div>}

        <button type="submit" disabled={isSubmitting || !image}>
          {isSubmitting ? 'Submitting...' : 'Generate Video'}
        </button>
      </form>
    </div>
  );
}
