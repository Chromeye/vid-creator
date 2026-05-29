export const getStatusColor = (status) => {
  switch (status) {
    case 'completed':
      return '#56bd52';
    case 'processing':
      return '#ff9800';
    case 'failed':
      return '#ea4335';
    default:
      return '#757575';
  }
};
export const getModelLabel = (model) => {
  switch (model) {
    case 'gemini-veo-31':
      return { name: 'Veo 3.1', className: 'pro' };
    case 'gemini-veo-31-fast':
      return { name: 'Veo 3.1 Fast', className: '' };
    case 'gemini-veo-3':
      return { name: 'Veo 3', className: 'pro' };
    case 'gemini-veo-3-fast':
      return { name: 'Veo 3 Fast', className: '' };
    case 'kling-v3-image-to-video':
      return { name: 'Kling 3.0 Standard', className: '' };
    case 'seedance-2-image-to-video':
      return { name: 'Seedance 2.0', className: '' };
    default:
      return { name: model, className: '' };
  }
};
