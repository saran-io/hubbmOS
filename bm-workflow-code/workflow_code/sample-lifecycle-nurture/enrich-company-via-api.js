exports.main = async (event, callback) => {
  const companyDomain = event.inputFields['company_domain'];
  if (!companyDomain) {
    throw new Error('Missing company domain');
  }
  // Fake enrichment
  const revenue = Math.floor(Math.random() * 1000000);
  callback({ outputFields: { enriched_revenue: revenue } });
};