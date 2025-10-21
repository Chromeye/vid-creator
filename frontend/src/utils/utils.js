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
    default:
      return model;
  }
};
