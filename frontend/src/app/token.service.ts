import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http'
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';
import { Token } from './token/token';

@Injectable({
  providedIn: 'root'
})

export class TokenService {

  constructor(private http: HttpClient) { 
  }

  public getToken() : Observable<Token>{
    return this.http.get<Token>( environment.apiUrl + '/token')
  }

  public saveToken(token) : Observable<Token>{
    return this.http.post<Token>( environment.apiUrl + '/token', token);
  }
}
