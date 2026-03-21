// GENERATED CODE -- DO NOT EDIT!

'use strict';
var grpc = require('@grpc/grpc-js');
var services_pb = require('./services_pb.js');

function serialize_kabrain_ApplyMutationsRequest(arg) {
  if (!(arg instanceof services_pb.ApplyMutationsRequest)) {
    throw new Error('Expected argument of type kabrain.ApplyMutationsRequest');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_ApplyMutationsRequest(buffer_arg) {
  return services_pb.ApplyMutationsRequest.deserializeBinary(new Uint8Array(buffer_arg));
}

function serialize_kabrain_ApplyMutationsResponse(arg) {
  if (!(arg instanceof services_pb.ApplyMutationsResponse)) {
    throw new Error('Expected argument of type kabrain.ApplyMutationsResponse');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_ApplyMutationsResponse(buffer_arg) {
  return services_pb.ApplyMutationsResponse.deserializeBinary(new Uint8Array(buffer_arg));
}

function serialize_kabrain_EnqueueJobRequest(arg) {
  if (!(arg instanceof services_pb.EnqueueJobRequest)) {
    throw new Error('Expected argument of type kabrain.EnqueueJobRequest');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_EnqueueJobRequest(buffer_arg) {
  return services_pb.EnqueueJobRequest.deserializeBinary(new Uint8Array(buffer_arg));
}

function serialize_kabrain_EnqueueJobResponse(arg) {
  if (!(arg instanceof services_pb.EnqueueJobResponse)) {
    throw new Error('Expected argument of type kabrain.EnqueueJobResponse');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_EnqueueJobResponse(buffer_arg) {
  return services_pb.EnqueueJobResponse.deserializeBinary(new Uint8Array(buffer_arg));
}

function serialize_kabrain_HealthCheckRequest(arg) {
  if (!(arg instanceof services_pb.HealthCheckRequest)) {
    throw new Error('Expected argument of type kabrain.HealthCheckRequest');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_HealthCheckRequest(buffer_arg) {
  return services_pb.HealthCheckRequest.deserializeBinary(new Uint8Array(buffer_arg));
}

function serialize_kabrain_HealthCheckResponse(arg) {
  if (!(arg instanceof services_pb.HealthCheckResponse)) {
    throw new Error('Expected argument of type kabrain.HealthCheckResponse');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_HealthCheckResponse(buffer_arg) {
  return services_pb.HealthCheckResponse.deserializeBinary(new Uint8Array(buffer_arg));
}

function serialize_kabrain_SubmitAgentTaskRequest(arg) {
  if (!(arg instanceof services_pb.SubmitAgentTaskRequest)) {
    throw new Error('Expected argument of type kabrain.SubmitAgentTaskRequest');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_SubmitAgentTaskRequest(buffer_arg) {
  return services_pb.SubmitAgentTaskRequest.deserializeBinary(new Uint8Array(buffer_arg));
}

function serialize_kabrain_SubmitAgentTaskResponse(arg) {
  if (!(arg instanceof services_pb.SubmitAgentTaskResponse)) {
    throw new Error('Expected argument of type kabrain.SubmitAgentTaskResponse');
  }
  return Buffer.from(arg.serializeBinary());
}

function deserialize_kabrain_SubmitAgentTaskResponse(buffer_arg) {
  return services_pb.SubmitAgentTaskResponse.deserializeBinary(new Uint8Array(buffer_arg));
}


var GraphServiceService = exports.GraphServiceService = {
  applyMutations: {
    path: '/kabrain.GraphService/ApplyMutations',
    requestStream: false,
    responseStream: false,
    requestType: services_pb.ApplyMutationsRequest,
    responseType: services_pb.ApplyMutationsResponse,
    requestSerialize: serialize_kabrain_ApplyMutationsRequest,
    requestDeserialize: deserialize_kabrain_ApplyMutationsRequest,
    responseSerialize: serialize_kabrain_ApplyMutationsResponse,
    responseDeserialize: deserialize_kabrain_ApplyMutationsResponse,
  },
};

exports.GraphServiceClient = grpc.makeGenericClientConstructor(GraphServiceService);
var HealthServiceService = exports.HealthServiceService = {
  check: {
    path: '/kabrain.HealthService/Check',
    requestStream: false,
    responseStream: false,
    requestType: services_pb.HealthCheckRequest,
    responseType: services_pb.HealthCheckResponse,
    requestSerialize: serialize_kabrain_HealthCheckRequest,
    requestDeserialize: deserialize_kabrain_HealthCheckRequest,
    responseSerialize: serialize_kabrain_HealthCheckResponse,
    responseDeserialize: deserialize_kabrain_HealthCheckResponse,
  },
};

exports.HealthServiceClient = grpc.makeGenericClientConstructor(HealthServiceService);
var AnalysisServiceService = exports.AnalysisServiceService = {
  enqueueJob: {
    path: '/kabrain.AnalysisService/EnqueueJob',
    requestStream: false,
    responseStream: false,
    requestType: services_pb.EnqueueJobRequest,
    responseType: services_pb.EnqueueJobResponse,
    requestSerialize: serialize_kabrain_EnqueueJobRequest,
    requestDeserialize: deserialize_kabrain_EnqueueJobRequest,
    responseSerialize: serialize_kabrain_EnqueueJobResponse,
    responseDeserialize: deserialize_kabrain_EnqueueJobResponse,
  },
};

exports.AnalysisServiceClient = grpc.makeGenericClientConstructor(AnalysisServiceService);
var AgentServiceService = exports.AgentServiceService = {
  submitAgentTask: {
    path: '/kabrain.AgentService/SubmitAgentTask',
    requestStream: false,
    responseStream: false,
    requestType: services_pb.SubmitAgentTaskRequest,
    responseType: services_pb.SubmitAgentTaskResponse,
    requestSerialize: serialize_kabrain_SubmitAgentTaskRequest,
    requestDeserialize: deserialize_kabrain_SubmitAgentTaskRequest,
    responseSerialize: serialize_kabrain_SubmitAgentTaskResponse,
    responseDeserialize: deserialize_kabrain_SubmitAgentTaskResponse,
  },
};

exports.AgentServiceClient = grpc.makeGenericClientConstructor(AgentServiceService);
