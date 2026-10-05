export default function handler(req, res) {
  res.status(200).json({
    status: "online",
    service: "HDFC Sky Recommendation Monitor",
    timestamp: new Date().toISOString(),
    endpoints: {
      cron: "/api/cron",
    },
  });
}
