import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../../../core/network/api_client.dart';
import '../models/product_response.dart';

part 'product_remote_source.g.dart';

abstract interface class ProductRemoteSource {
  Future<List<ProductResponse>> fetchProducts({String? query});

  Future<ProductResponse> fetchProduct(int id);
}

class ProductRemoteSourceImpl implements ProductRemoteSource {
  const ProductRemoteSourceImpl(this._dio);

  final Dio _dio;

  @override
  Future<List<ProductResponse>> fetchProducts({String? query}) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '/products',
        queryParameters: {if (query != null && query.isNotEmpty) 'q': query},
      );
      return response.data!
          .cast<Map<String, dynamic>>()
          .map(ProductResponse.fromJson)
          .toList();
    } on DioException catch (e) {
      throw AppException.fromDio(e);
    }
  }

  @override
  Future<ProductResponse> fetchProduct(int id) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/products/$id');
      return ProductResponse.fromJson(response.data!);
    } on DioException catch (e) {
      throw AppException.fromDio(e);
    }
  }
}

@riverpod
ProductRemoteSource productRemoteSource(Ref ref) =>
    ProductRemoteSourceImpl(ref.watch(apiClientProvider));
