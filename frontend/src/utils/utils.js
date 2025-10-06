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
