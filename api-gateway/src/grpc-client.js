import grpc from '@grpc/grpc-js';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const servicesGrpc = require('../proto/node/services_grpc_pb.js');
const servicesPb = require('../proto/node/services_pb.js');

export const healthClient = new servicesGrpc.HealthServiceClient(
  'graph-service:50051',
  grpc.credentials.createInsecure()
);

export const makeHealthRequest = (service = 'graph-service') => {
  const req = new servicesPb.HealthCheckRequest();
  req.setService(service);
  return req;
};
