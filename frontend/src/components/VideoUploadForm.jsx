import { useState, useRef } from 'react';
import { useMyContext } from '../context/context-provider';

export default function VideoUploadForm({ onSubmit }) {
  const context = useMyContext();
  const [image, setImage] = useState({});
  const [preview, setPreview] = useState({});
  const [showFinalFrame, setShowFinalFrame] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState({});

  const formRef = useRef(null);

  const handleImageChange = (e, position) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      setError((current) => ({ ...current, [position || 'start']: 'Please upload a JPG or PNG file' }));
      return;
    }

    // Validate dimensions
    const img = new Image();
    img.onload = () => {
      if (img.width !== 1280 || img.height !== 720) {
        setError((current) => ({ ...current, [position || 'start']: 'Image must be 1280x720 pixels' }));
        setImage((current) => ({ ...current, [position || 'start']: null }));
        setPreview((current) => ({ ...current, [position || 'start']: null }));
      } else {
        setError((current) => ({ ...current, [position || 'start']: '' }));
        setImage((current) => ({ ...current, [position || 'start']: file }));
        setPreview((current) => ({
          ...current,
          [position || 'start']: URL.createObjectURL(file),
        }));
      }
    };
    img.src = URL.createObjectURL(file);
  };
  const isEmptyObject = (obj) => (Object.keys(obj).length === 0 || Object.keys(obj).every((key) => obj[key] == null)) && obj.constructor === Object;
  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!context.data.prompt || !image.start) {
      setError((current) => ({ ...current, general: 'Please provide both a prompt and an image' }));
      return;
    }

    setIsSubmitting(true);
    setError({});

    try {
      await onSubmit({ prompt: context.data.prompt, image, model: context.data.model });
      // Reset form after successful submission
      context.updateValue('prompt', '');
      setImage({});
      setPreview({});
    } catch (err) {
      setError((current) => ({ ...current, general: err.message || 'Failed to submit request' }));
    } finally {
      setIsSubmitting(false);
      if (formRef.current) {
        formRef.current.reset();
      }
    }
  };
  return (
    <div className='upload-form'>
      <h2>Generate Video with Gemini Veo 3</h2>

      <form onSubmit={handleSubmit} ref={formRef} className='form-body'>
        <div className='form-group'>
          <label htmlFor='model'>Model:</label>
          <select
            id='model'
            value={context.data.model || 'gemini-veo-31-fast'}
            className='model-options'
            onChange={(e) => context.updateValue('model', e.target.value)}
            disabled={isSubmitting}
          >
            <option value='gemini-veo-31-fast'>Gemini Veo 3.1 Fast</option>
            <option value='gemini-veo-31'>Gemini Veo 3.1</option>
          </select>
        </div>
        <div className='form-group'>
          <label htmlFor='prompt'>Prompt:</label>
          <textarea
            id='prompt'
            value={context.data.prompt || ''}
            onChange={(e) => context.updateValue('prompt', e.target.value)}
            placeholder='Describe the video you want to generate...'
            rows='4'
            disabled={isSubmitting}
            required
          />
        </div>

        <div className='form-group'>
          <label htmlFor='image'>Start frame referenence (1280x720, JPG/PNG):</label>
          <input id='image' type='file' accept='image/jpeg,image/png' onChange={handleImageChange} disabled={isSubmitting} required />
          {error.start && <p className='error-message'>{error.start}</p>}
        </div>
        <div className='form-group final-frame-option'>
          <input
            type='checkbox'
            id='finalFrame'
            disabled={isSubmitting}
            checked={showFinalFrame}
            onChange={(e) => {
              setShowFinalFrame(e.target.checked);
              if (!e.target.checked) {
                setImage((current) => ({ ...current, end: null }));
                setPreview((current) => ({ ...current, end: null }));
              }
            }}
          />
          <label htmlFor='finalFrame'>Use image reference for the final frame, too?</label>
        </div>
        {showFinalFrame && (
          <div className='form-group'>
            <label htmlFor='finalFrame'>Final frame reference (1280x720, JPG/PNG):</label>
            <input id='image' type='file' accept='image/jpeg,image/png' onChange={(e) => handleImageChange(e, 'end')} disabled={isSubmitting} required />
            {error.end && <p className='error-message'>{error.end}</p>}
          </div>
        )}

        {!isEmptyObject(preview) && (
          <div className='image-previews'>
            {preview.start && <img src={preview.start} alt='First Frame Preview' />}

            {preview.end && <img src={preview.end} alt='Final Frame Preview' />}
          </div>
        )}
        {error.general && <p className='error-message'>{error.general}</p>}
        <button type='submit' disabled={isSubmitting || !(image.start && context.data.prompt) || (showFinalFrame && !image.end)}>
          {isSubmitting ? 'Submitting...' : 'Generate Video'}
        </button>
      </form>
    </div>
  );
}
