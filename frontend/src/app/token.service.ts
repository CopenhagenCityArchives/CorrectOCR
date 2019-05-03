import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http'
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';
import { TokenModel } from './token/token.model';

@Injectable({
  providedIn: 'root'
})
export class TokenService {

  constructor(private http: HttpClient) { 
  }

  public getToken() : Observable<any>{
    return this.http.get( environment + '/token')
  }

  public saveToken(token) : Observable<any>{
    return this.http.post( environment + '/token', token);
  }
}
